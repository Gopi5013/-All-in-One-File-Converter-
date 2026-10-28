from pdf2docx import Converter

pdf_file = "download.pdf"
docx_file = "output.docx"

cv = Converter(pdf_file)
cv.convert(docx_file)
cv.close()

print("Conversion completed successfully!")
