

import os
from PIL import Image

folder = input("Folder path: ")

os.makedirs("resized", exist_ok=True)

for filename in os.listdir(folder):
    if filename.lower().endswith((".jpg", ".jpeg", ".png")):
        img = Image.open(os.path.join(folder, filename))

        resized_img = img.resize((800, 600))

        resized_img.save(os.path.join("resized", filename))

print("All images resized")
