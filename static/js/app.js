const searchInput = document.querySelector("#tool-search");

if (searchInput) {
  const toolCards = [...document.querySelectorAll("[data-tool-card]")];
  const categories = [...document.querySelectorAll("[data-tool-category]")];
  const filterButtons = [...document.querySelectorAll("[data-tool-filter]")];
  const clearButton = document.querySelector(".search-clear");
  const emptyState = document.querySelector(".empty-state");
  const resultsCount = document.querySelector(".results-count");
  let activeCategory = "all";

  function updateTools() {
    const query = searchInput.value.trim().toLocaleLowerCase();
    let visibleCount = 0;

    for (const card of toolCards) {
      const matchesText = card.dataset.search.toLocaleLowerCase().includes(query);
      const matchesCategory = activeCategory === "all" || card.dataset.category === activeCategory;
      const isVisible = matchesText && matchesCategory;

      card.hidden = !isVisible;
      visibleCount += Number(isVisible);
    }

    for (const category of categories) {
      const hasVisibleCards = category.querySelector("[data-tool-card]:not([hidden])");
      category.hidden = !hasVisibleCards;
    }

    emptyState.hidden = visibleCount > 0;
    resultsCount.textContent = query || activeCategory !== "all"
      ? `${visibleCount} ${visibleCount === 1 ? "tool" : "tools"} shown`
      : "";
    clearButton.hidden = query.length === 0;
  }

  searchInput.addEventListener("input", updateTools);

  clearButton.addEventListener("click", () => {
    searchInput.value = "";
    searchInput.focus();
    updateTools();
  });

  for (const button of filterButtons) {
    button.addEventListener("click", () => {
      activeCategory = button.dataset.toolFilter;

      for (const filterButton of filterButtons) {
        const isActive = filterButton === button;
        filterButton.classList.toggle("is-active", isActive);
        filterButton.setAttribute("aria-pressed", String(isActive));
      }

      updateTools();
    });
  }

  updateTools();
}

const resizeForm = document.querySelector("#resize-form");

if (resizeForm) {
  const imageInput = document.querySelector("#image-file");
  const dropZone = document.querySelector("#upload-dropzone");
  const fileDetails = document.querySelector("#file-details");
  const preview = document.querySelector("#image-preview");
  const previewImage = document.querySelector("#image-preview-content");
  const submitButton = document.querySelector("#resize-submit");
  const processingStatus = document.querySelector("#processing-status");
  let previewUrl = null;

  function clearPreview() {
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
      previewUrl = null;
    }

    previewImage.removeAttribute("src");
    previewImage.alt = "";
    preview.hidden = true;
    fileDetails.textContent = "";
    fileDetails.hidden = true;
  }

  function showPreview(file) {
    clearPreview();
    if (!file) {
      return;
    }

    fileDetails.textContent = `${file.name} · ${(file.size / (1024 * 1024)).toFixed(2)} MB`;
    fileDetails.hidden = false;
    previewUrl = URL.createObjectURL(file);
    previewImage.src = previewUrl;
    previewImage.alt = `Preview of ${file.name}`;
    preview.hidden = false;
  }

  imageInput.addEventListener("change", () => {
    showPreview(imageInput.files[0]);
  });

  for (const eventName of ["dragenter", "dragover"]) {
    dropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropZone.classList.add("is-dragging");
    });
  }

  for (const eventName of ["dragleave", "drop"]) {
    dropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropZone.classList.remove("is-dragging");
    });
  }

  dropZone.addEventListener("drop", (event) => {
    const [file] = event.dataTransfer.files;
    if (!file) {
      return;
    }

    imageInput.files = event.dataTransfer.files;
    showPreview(file);
  });

  resizeForm.addEventListener("submit", () => {
    submitButton.disabled = true;
    submitButton.textContent = "Resizing…";
    processingStatus.hidden = false;
  });

  resizeForm.addEventListener("reset", () => {
    window.setTimeout(() => {
      clearPreview();
      submitButton.disabled = false;
      submitButton.textContent = "Resize image";
      processingStatus.hidden = true;
    });
  });

  window.addEventListener("pagehide", () => {
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
    }
  });
}

const mergeForm = document.querySelector("#merge-form");

if (mergeForm) {
  const pdfInput = document.querySelector("#pdf-files");
  const dropZone = document.querySelector("#pdf-dropzone");
  const fileList = document.querySelector("#pdf-file-list");
  const fileSummary = document.querySelector("#pdf-file-summary");
  const submitButton = document.querySelector("#merge-submit");
  const processingStatus = document.querySelector("#merge-processing-status");
  let selectedFiles = [];

  function syncFileInput() {
    const dataTransfer = new DataTransfer();
    for (const file of selectedFiles) {
      dataTransfer.items.add(file);
    }
    pdfInput.files = dataTransfer.files;
  }

  function renderFileList() {
    fileList.replaceChildren();
    fileSummary.textContent = selectedFiles.length
      ? `${selectedFiles.length} ${selectedFiles.length === 1 ? "PDF" : "PDFs"} selected.`
      : "No files selected.";

    selectedFiles.forEach((file, index) => {
      const item = document.createElement("li");
      item.className = "selected-pdf-item";

      const details = document.createElement("div");
      details.className = "selected-pdf-details";
      const name = document.createElement("span");
      name.className = "selected-pdf-name";
      name.textContent = file.name;
      const size = document.createElement("span");
      size.className = "selected-pdf-size";
      size.textContent = `${(file.size / (1024 * 1024)).toFixed(2)} MB`;
      details.append(name, size);

      const controls = document.createElement("div");
      controls.className = "selected-pdf-controls";
      const moveUp = document.createElement("button");
      moveUp.type = "button";
      moveUp.textContent = "Up";
      moveUp.setAttribute("aria-label", `Move ${file.name} up`);
      moveUp.disabled = index === 0;
      moveUp.addEventListener("click", () => moveFile(index, -1));

      const moveDown = document.createElement("button");
      moveDown.type = "button";
      moveDown.textContent = "Down";
      moveDown.setAttribute("aria-label", `Move ${file.name} down`);
      moveDown.disabled = index === selectedFiles.length - 1;
      moveDown.addEventListener("click", () => moveFile(index, 1));

      const remove = document.createElement("button");
      remove.type = "button";
      remove.textContent = "Remove";
      remove.setAttribute("aria-label", `Remove ${file.name}`);
      remove.addEventListener("click", () => {
        selectedFiles = selectedFiles.filter((_, fileIndex) => fileIndex !== index);
        syncFileInput();
        renderFileList();
      });

      controls.append(moveUp, moveDown, remove);
      item.append(details, controls);
      fileList.append(item);
    });
  }

  function moveFile(index, direction) {
    const destination = index + direction;
    if (destination < 0 || destination >= selectedFiles.length) {
      return;
    }

    [selectedFiles[index], selectedFiles[destination]] = [
      selectedFiles[destination],
      selectedFiles[index],
    ];
    syncFileInput();
    renderFileList();
  }

  function updateSelectedFiles(files) {
    selectedFiles = [...files];
    syncFileInput();
    renderFileList();
  }

  pdfInput.addEventListener("change", () => {
    updateSelectedFiles(pdfInput.files);
  });

  for (const eventName of ["dragenter", "dragover"]) {
    dropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropZone.classList.add("is-dragging");
    });
  }

  for (const eventName of ["dragleave", "drop"]) {
    dropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropZone.classList.remove("is-dragging");
    });
  }

  dropZone.addEventListener("drop", (event) => {
    if (event.dataTransfer.files.length) {
      updateSelectedFiles(event.dataTransfer.files);
    }
  });

  mergeForm.addEventListener("submit", () => {
    submitButton.disabled = true;
    submitButton.textContent = "Merging…";
    processingStatus.hidden = false;
  });

  mergeForm.addEventListener("reset", () => {
    window.setTimeout(() => {
      selectedFiles = [];
      renderFileList();
      submitButton.disabled = false;
      submitButton.textContent = "Merge PDFs";
      processingStatus.hidden = true;
    });
  });
}

const pdfToWordForm = document.querySelector("#pdf-to-word-form");

if (pdfToWordForm) {
  const pdfInput = document.querySelector("#pdf-word-file");
  const dropZone = document.querySelector("#pdf-word-dropzone");
  const fileDetails = document.querySelector("#pdf-word-file-details");
  const submitButton = document.querySelector("#pdf-word-submit");
  const processingStatus = document.querySelector("#pdf-word-processing-status");

  function showSelectedFile(file) {
    fileDetails.textContent = file
      ? `${file.name} · ${(file.size / (1024 * 1024)).toFixed(2)} MB`
      : "";
    fileDetails.hidden = !file;
  }

  pdfInput.addEventListener("change", () => {
    showSelectedFile(pdfInput.files[0]);
  });

  for (const eventName of ["dragenter", "dragover"]) {
    dropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropZone.classList.add("is-dragging");
    });
  }

  for (const eventName of ["dragleave", "drop"]) {
    dropZone.addEventListener(eventName, (event) => {
      event.preventDefault();
      dropZone.classList.remove("is-dragging");
    });
  }

  dropZone.addEventListener("drop", (event) => {
    const [file] = event.dataTransfer.files;
    if (!file) {
      return;
    }

    pdfInput.files = event.dataTransfer.files;
    showSelectedFile(file);
  });

  pdfToWordForm.addEventListener("submit", () => {
    submitButton.disabled = true;
    submitButton.textContent = "Converting…";
    processingStatus.hidden = false;
  });

  pdfToWordForm.addEventListener("reset", () => {
    window.setTimeout(() => {
      showSelectedFile(null);
      submitButton.disabled = false;
      submitButton.textContent = "Convert to Word";
      processingStatus.hidden = true;
    });
  });
}
