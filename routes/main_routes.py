from flask import Blueprint, render_template

main_bp = Blueprint("main", __name__)

TOOLS_BY_CATEGORY = [
    {
        "id": "pdf",
        "name": "PDF tools",
        "description": "Convert, organize, and prepare PDF documents.",
        "tools": [
            {
                "name": "PDF to Word",
                "description": "Convert PDF pages into an editable Word document.",
                "icon": "PDF",
                "keywords": "convert docx editable",
                "endpoint": "pdf.pdf_to_word_page",
            },
            {
                "name": "Merge PDF",
                "description": "Combine multiple PDF files into one document.",
                "icon": "PDF",
                "keywords": "join combine",
                "endpoint": "pdf.merge_pdf_page",
            },
            {
                "name": "Split PDF",
                "description": "Separate a PDF into pages or selected ranges.",
                "icon": "PDF",
                "keywords": "divide pages range",
                "endpoint": "pdf.split_pdf_page",
            },
            {
                "name": "Compress PDF",
                "description": "Reduce file size where the PDF content allows.",
                "icon": "PDF",
                "keywords": "shrink optimize",
                "endpoint": "pdf.compress_pdf_page",
            },
            {
                "name": "Extract PDF pages",
                "description": "Save selected pages as a new PDF.",
                "icon": "PDF",
                "keywords": "select pages",
                "endpoint": "pdf.extract_pdf_pages_page",
            },
            {
                "name": "Rotate PDF",
                "description": "Turn pages to the correct orientation.",
                "icon": "PDF",
                "keywords": "orientation",
                "endpoint": "pdf.rotate_pdf_page",
            },
            {
                "name": "Images to PDF",
                "description": "Place one or more images into a PDF.",
                "icon": "PDF",
                "keywords": "jpg png photo",
                "endpoint": "pdf.images_to_pdf_page",
            },
            {
                "name": "Word to PDF",
                "description": "Export a Word document as a PDF using a local office engine.",
                "icon": "PDF",
                "keywords": "docx export convert",
                "endpoint": "pdf.word_to_pdf_page",
            },
        ],
    },
    {
        "id": "image",
        "name": "Image tools",
        "description": "Resize, convert, and refine your images.",
        "tools": [
            {
                "name": "Resize image",
                "description": "Set custom image dimensions with optional aspect ratio lock.",
                "icon": "IMG",
                "keywords": "width height scale",
                "endpoint": "image.resize_image_page",
            },
            {
                "name": "Compress image",
                "description": "Adjust image quality to create a smaller file.",
                "icon": "IMG",
                "keywords": "quality optimize",
                "endpoint": "image.compress_image_page",
            },
            {
                "name": "Convert image",
                "description": "Convert between JPG, PNG, and WebP formats.",
                "icon": "IMG",
                "keywords": "jpg jpeg png webp format",
                "endpoint": "image.convert_image_page",
            },
            {
                "name": "Pencil sketch",
                "description": "Create a pencil-style sketch from a photograph.",
                "icon": "IMG",
                "keywords": "draw photo effect",
                "endpoint": "image.pencil_sketch_page",
            },
            {
                "name": "Crop and rotate",
                "description": "Crop an image or rotate it to a new orientation.",
                "icon": "IMG",
                "keywords": "edit turn",
                "endpoint": "image.crop_rotate_image_page",
            },
        ],
    },
]


@main_bp.get("/")
def index():
    tool_count = sum(len(category["tools"]) for category in TOOLS_BY_CATEGORY)
    available_tool_count = sum(
        bool(tool.get("endpoint"))
        for category in TOOLS_BY_CATEGORY
        for tool in category["tools"]
    )
    return render_template(
        "index.html",
        tools_by_category=TOOLS_BY_CATEGORY,
        tool_count=tool_count,
        available_tool_count=available_tool_count,
    )
