

from pypdf import PdfWriter
import glob

merger = PdfWriter()

for pdf in sorted(glob.glob("*.pdf")):
    merger.append(pdf)

merger.write("merged.pdf")
merger.close()

print("Merged PDF created successfully")
