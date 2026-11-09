import Tesseract from 'tesseract.js'
import * as pdfjs from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl

const IMAGE_TYPES = /^image\/(png|jpe?g|webp|bmp|gif|tiff?)$/i

export type Progress = (fraction: number, label: string) => void
export interface Extraction {
  text: string
  pages: number
  method: 'text' | 'ocr' | 'text-layer'
}

export function isSupported(file: File): boolean {
  return file.type === 'application/pdf' || IMAGE_TYPES.test(file.type) || file.type.startsWith('text/')
}

async function ocrImage(source: File | HTMLCanvasElement, onProgress?: (p: number) => void): Promise<string> {
  const { data } = await Tesseract.recognize(source, 'eng', {
    logger: (m: { status: string; progress: number }) => {
      if (m.status === 'recognizing text') onProgress?.(m.progress)
    },
  })
  return data.text.trim()
}

/** Client-side extraction (interim). The FastAPI service will replace this with PyMuPDF/python-docx/openpyxl. */
export async function extractText(file: File, onProgress?: Progress): Promise<Extraction> {
  if (file.type.startsWith('text/')) {
    onProgress?.(1, 'Reading text')
    return { text: await file.text(), pages: 1, method: 'text' }
  }

  if (IMAGE_TYPES.test(file.type)) {
    const text = await ocrImage(file, (p) => onProgress?.(p, 'Running OCR'))
    return { text, pages: 1, method: 'ocr' }
  }

  if (file.type === 'application/pdf') {
    const pdf = await pdfjs.getDocument({ data: await file.arrayBuffer() }).promise
    const parts: string[] = []
    let usedOcr = false
    for (let i = 1; i <= pdf.numPages; i++) {
      const page = await pdf.getPage(i)
      const content = await page.getTextContent()
      let text = content.items.map((it) => ('str' in it ? it.str : '')).join(' ').trim()

      // Scanned page (no text layer): render and OCR it.
      if (text.length < 20) {
        usedOcr = true
        const viewport = page.getViewport({ scale: 2 })
        const canvas = document.createElement('canvas')
        canvas.width = viewport.width
        canvas.height = viewport.height
        await page.render({ canvas, canvasContext: canvas.getContext('2d')!, viewport }).promise
        text = await ocrImage(canvas, (p) =>
          onProgress?.((i - 1 + p) / pdf.numPages, `OCR page ${i}/${pdf.numPages}`),
        )
      } else {
        onProgress?.(i / pdf.numPages, `Reading page ${i}/${pdf.numPages}`)
      }
      parts.push(`--- Page ${i} ---\n${text}`)
    }
    return { text: parts.join('\n\n'), pages: pdf.numPages, method: usedOcr ? 'ocr' : 'text-layer' }
  }

  throw new Error('Unsupported file type')
}
