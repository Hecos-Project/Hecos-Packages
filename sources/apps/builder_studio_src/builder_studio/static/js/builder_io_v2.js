window.builderPickNativeImage = async function() {
    const dir = document.getElementById('builder-source-dir').value;
    if (!dir) {
        _builderModal("Please load a package directory first.", true);
        return;
    }
    try {
        const resp = await fetch('/api/system/explorer/pick-native', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ 
                title: "Select Preview Image", 
                filetypes: [["PNG Images", "*.png"]] 
            })
        });
        const data = await resp.json();
        if (data && data.path) {
            const addResp = await fetch('/api/hpm/builder/add-image', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ src_dir: dir, image_path: data.path })
            });
            const addData = await addResp.json();
            if (!addData.ok) {
                _builderModal("Failed to add image: " + addData.error, true);
            } else {
                _builderUpdateImages(dir, addData.images);
                if (typeof window.builderRefreshSources === 'function') setTimeout(() => window.builderRefreshSources(), 100);
            }
        }
    } catch (e) {
        console.error("Native image picker error", e);
    }
};

window.builderUploadImage = async function(event) {
    const dir = document.getElementById('builder-source-dir').value;
    if (!dir) {
        _builderModal("Please select a package directory first.", true);
        return;
    }
    
    const file = event.target.files[0];
    if (!file) return;
    
    const formData = new FormData();
    formData.append('src_dir', dir);
    formData.append('file', file);
    
    try {
        const resp = await fetch('/api/hpm/builder/add-image-upload', {
            method: 'POST',
            body: formData
        });
        const data = await resp.json();
        if (!data.ok) {
            _builderModal("Failed to upload image: " + data.error, true);
        } else {
            _builderUpdateImages(dir, data.images);
            if (typeof window.builderRefreshSources === 'function') setTimeout(() => window.builderRefreshSources(), 100);
        }
    } catch (e) {
        console.error("Image upload error", e);
    }
    event.target.value = ''; // Reset input
};

window.builderDeleteImage = function(imageName) {
    const dir = document.getElementById('builder-source-dir').value;
    if (!dir || !imageName) return;
    
    _builderConfirmModal(`Are you sure you want to delete ${imageName}?`, async () => {
        try {
            const resp = await fetch('/api/hpm/builder/delete-image-upload', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ src_dir: dir, image_name: imageName })
            });
            const data = await resp.json();
            if (!data.ok) {
                _builderModal("Failed to delete image: " + data.error, true);
            } else {
                _builderUpdateImages(dir, data.images);
                if (typeof window.builderRefreshSources === 'function') setTimeout(() => window.builderRefreshSources(), 100);
            }
        } catch (e) {
            console.error("Image delete error", e);
        }
    });
};

window.builderHandleFolderInput = function(e) {
    if (e.target.files && e.target.files.length > 0) {
        let packageNames = new Set();
        
        for (let i = 0; i < e.target.files.length; i++) {
            let f = e.target.files[i];
            if (f.webkitRelativePath && f.webkitRelativePath.endsWith('hpkg_manifest.toml')) {
                let parts = f.webkitRelativePath.split('/');
                if (parts.length >= 2) {
                    packageNames.add(parts[parts.length - 2]);
                }
            }
        }
        
        let packagesFound = Array.from(packageNames);
        
        if (packagesFound.length === 0) {
            let f = e.target.files[0];
            let folderName = f.webkitRelativePath ? f.webkitRelativePath.split('/')[0] : "";
            if (folderName) {
                _builderSelectFolderByName(folderName);
            } else {
                _builderModal("No packages found in this folder.", true);
            }
        } else if (packagesFound.length === 1) {
            _builderSelectFolderByName(packagesFound[0]);
        } else {
            _builderStartBatchMode(packagesFound);
        }
    }
    e.target.value = ''; 
};

window.builderHandleFolderDrop = function(e, element) {
    e.preventDefault();
    e.stopPropagation();
    element.style.borderColor = '';
    
    // Some browsers provide absolute path via f.path (like Electron)
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        let f = e.dataTransfer.files[0];
        if (f.path) {
            let parts = f.path.split(/[\\/]/);
            _builderSelectFolderByName(parts[parts.length-1]);
        } else if (f.name) {
            // Drop in web browser might just give the folder name
            _builderSelectFolderByName(f.name);
        }
    }
};

window._builderSelectFolderByName = function(folderName) {
    if (!window.builderSourcesData) return;
    
    let found = window.builderSourcesData.find(src => src.rel_path.includes(folderName) || src.name.includes(folderName));
    
    if (found) {
        const baseDir = document.getElementById('builder-sources-root') ? document.getElementById('builder-sources-root').value : '';
        let d = baseDir;
        if (!d.endsWith("\\") && !d.endsWith("/")) d += "\\";
        document.getElementById('builder-source-dir').value = d + found.rel_path;
        
        window.builderLoadManifest();
        // Scroll removed because we have a fixed right pane
    } else {
        _builderModal("Folder '" + folderName + "' not found! Make sure it is located in the configured Sources root.", true);
    }
};

let currentPickerTarget = null;
let currentPickerPath = '';

window.builderPickSourcesRoot = function() {
    window.builderShowCustomPicker('builder-sources-root');
};

window.builderPickDestRoot = function() {
    window.builderShowCustomPicker('builder-dest-root');
};

window.builderShowCustomPicker = async function(targetId) {
    const inputEl = document.getElementById(targetId);
    if (!inputEl) return;
    
    const currentVal = inputEl.value || '';
    // Determine if this is a file picker (private key) or folder picker
    const isFilePicker = targetId === 'setup-private-key';
    
    try {
        const resp = await fetch('/api/system/explorer/pick-native', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                title: isFilePicker ? 'Select File' : 'Select Directory',
                initialdir: currentVal,
                pick_dir: !isFilePicker,
                filetypes: isFilePicker ? [["PEM Key Files", "*.pem"], ["All Files", "*.*"]] : undefined
            })
        });
        const data = await resp.json();
        if (data && data.ok && data.path) {
            inputEl.value = data.path;
            if (targetId === 'builder-sources-root' || targetId === 'setup-sources-root') {
                window.builderRefreshSources();
            }
        }
    } catch(e) {
        console.error('Picker error:', e);
        window.builderLog('Error opening file picker: ' + e.message, 'error');
    }
};
