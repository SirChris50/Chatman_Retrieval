# chatman_retrieval.spec
# ----------------------
# PyInstaller spec for the Chatman Retrieval app.
#
# Build with:   pyinstaller chatman_retrieval.spec --noconfirm
#
# Output:  dist\ChatmanRetrieval\
#          Copy data\ and model_cache\ there before distributing.

import sys
from PyInstaller.utils.hooks import collect_all, collect_data_files

# PyTorch has deep dependency chains — the default limit causes RecursionError.
sys.setrecursionlimit(sys.getrecursionlimit() * 5)

block_cipher = None

# ---------------------------------------------------------------------------
# Collect heavyweight packages that PyInstaller cannot fully auto-detect.
# collect_all() returns (datas, binaries, hiddenimports) for each package.
# ---------------------------------------------------------------------------
st_d,  st_b,  st_h  = collect_all('sentence_transformers')
tr_d,  tr_b,  tr_h  = collect_all('transformers')
tok_d, tok_b, tok_h = collect_all('tokenizers')
hf_d,  hf_b,  hf_h  = collect_all('huggingface_hub')
ch_d,  ch_b,  ch_h  = collect_all('chromadb')

# ---------------------------------------------------------------------------
# PyTorch — must be fully collected so c10.dll and friends are bundled.
# include_py_files=True keeps source files needed for TorchScript / JIT.
# WinError 1114 (DLL init failed) occurs when these DLLs are absent.
# ---------------------------------------------------------------------------
torch_d, torch_b, torch_h = collect_all('torch', include_py_files=True)

# ---------------------------------------------------------------------------
a = Analysis(
    ['run.py'],
    pathex=[r'D:\Chatman_Retrieval'],
    binaries=[] + st_b + tr_b + tok_b + hf_b + ch_b + torch_b,
    datas=[
        # Flask templates and static assets — copied into the bundle root
        ('templates', 'templates'),
        ('static',    'static'),
        # The app package itself (app.py + retrieval_engine.py)
        ('app',       'app'),
    ] + st_d + tr_d + tok_d + hf_d + ch_d + torch_d,
    hiddenimports=[
        # App
        'app.app',
        'app.retrieval_engine',
        # Flask ecosystem
        'flask',
        'jinja2',
        'jinja2.ext',
        'werkzeug',
        'werkzeug.serving',
        'werkzeug.debug',
        'click',
        # Retrieval
        'rapidfuzz',
        'rapidfuzz.fuzz',
        'rapidfuzz.process',
        # Numeric / ML
        'numpy',
        'scipy',
        'scipy.spatial',
        'scipy.spatial.distance',
        'sklearn',
        'sklearn.preprocessing',
        'tqdm',
        'tqdm.auto',
        # PyTorch core C extensions — required for DLL init
        'torch',
        'torch._C',
        'torch._C._jit',
        'torch.jit',
        # ChromaDB internals that are commonly missed
        'hnswlib',
        'posthog',
        'overrides',
        'pydantic',
        'pydantic.v1',
        'typing_extensions',
        # Standard lib (ensure sqlite3 DLL is picked up)
        'sqlite3',
        '_sqlite3',
    ] + st_h + tr_h + tok_h + hf_h + ch_h + torch_h,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # copy_metadata bundles torch's dist-info so importlib.metadata queries work.
    copy_metadata=['torch'],
    excludes=[
        # Exclude CUDA / GPU libs to keep the bundle smaller.
        # The app runs on CPU only.
        'torch.cuda',
        'caffe2',
        'onnxruntime',
        'tensorboard',
        'torchvision',
        'torchaudio',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Keep torch source files in the bundle (required for TorchScript).
# 'py' mode prevents byte-compilation that breaks JIT source inspection.
a.module_collection_mode = {
    'torch': 'py',
}

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ChatmanRetrieval',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX can corrupt torch DLLs — leave off
    console=True,       # Keep console so startup messages are visible.
                        # Change to False once you're happy it works.
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,          # Set to 'path/to/icon.ico' if you have one
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='ChatmanRetrieval',
)
