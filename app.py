from flask import Flask, request, send_file, render_template_string
from flask_cors import CORS
from PIL import Image
import io
import os
import subprocess
import tempfile
import platform
import traceback
import shutil

app = Flask(__name__)
CORS(app)  # This enables Netlify to talk to your PC

def get_gs_command():
    if platform.system() == 'Windows':
        return 'gswin64c'
    return 'gs'

def compress_image(file, level):
    img = Image.open(file)
    
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
        
    output = io.BytesIO()
    
    if level == 'low':
        img.save(output, format='JPEG', quality=85, optimize=True)
    elif level == 'mid':
        img.save(output, format='JPEG', quality=50, optimize=True)
    elif level == 'high':
        # Resize aggressively if high compression is requested
        max_size = 1200
        if img.width > max_size or img.height > max_size:
            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        img.save(output, format='JPEG', quality=20, optimize=True)
        
    output.seek(0)
    return output, 'image/jpeg', 'compressed_image.jpg'

def compress_pdf(file, level):
    gs_cmd = get_gs_command()
    
    # 1. DIAGNOSTIC CHECK: Verify Windows can actually see Ghostscript
    if not shutil.which(gs_cmd):
        raise Exception(f"CRITICAL ERROR: Python cannot find '{gs_cmd}' in your System PATH. Windows doesn't know Ghostscript is installed.")

    if level == 'low':
        pdf_settings = '/printer'
    elif level == 'mid':
        pdf_settings = '/ebook'
    elif level == 'high':
        pdf_settings = '/screen'
    else:
        pdf_settings = '/ebook'

    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_in:
        temp_in.write(file.read())
        temp_in_path = temp_in.name

    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_out:
        temp_out_path = temp_out.name

    try:
        command = [
            gs_cmd,
            '-sDEVICE=pdfwrite',
            '-dCompatibilityLevel=1.4',
            f'-dPDFSETTINGS={pdf_settings}',
            '-dNOPAUSE',
            '-dQUIET',
            '-dBATCH',
            f'-sOutputFile={temp_out_path}',
            temp_in_path
        ]
        
        # 2. Run the command and capture any deep system errors
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        
        with open(temp_out_path, 'rb') as f:
            output = io.BytesIO(f.read())
            
        output.seek(0)
        return output, 'application/pdf', 'compressed_document.pdf'
        
    except subprocess.CalledProcessError as e:
        # If Ghostscript runs but crashes, this prints its internal error log
        raise Exception(f"Ghostscript execution failed. Error log: {e.stderr}")
    finally:
        if os.path.exists(temp_in_path):
            os.remove(temp_in_path)
        if os.path.exists(temp_out_path):
            os.remove(temp_out_path)

@app.route('/compress', methods=['POST'])
def compress_file():
    if 'file' not in request.files:
        return "No file uploaded", 400
        
    file = request.files['file']
    level = request.form.get('level', 'mid')
    
    if file.filename == '':
        return "No selected file", 400

    file_ext = file.filename.split('.')[-1].lower()

    try:
        if file_ext in ['jpg', 'jpeg', 'png', 'webp', 'bmp']:
            output, mimetype, out_name = compress_image(file, level)
        elif file_ext == 'pdf':
            output, mimetype, out_name = compress_pdf(file, level)
        else:
            return "Unsupported file type. Please upload an Image or PDF.", 400

        return send_file(
            output,
            mimetype=mimetype,
            as_attachment=True,
            download_name=out_name
        )
    except Exception as e:
        print("--- ERROR OCCURRED ---")
        traceback.print_exc()
        return str(e), 500

@app.route('/')
def index():
    return send_file('index.html')

if __name__ == '__main__':
    app.run(debug=True, port=5000)