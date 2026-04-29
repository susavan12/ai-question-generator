import json
import os
import io
import pdfplumber

from flask import Flask, render_template, request, jsonify, send_file
from groq import Groq

from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm

from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)

# ---------------- API KEY ----------------
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
print("GROQ KEY LOADED:", bool(GROQ_API_KEY))

client = Groq(api_key=GROQ_API_KEY)

# ---------------- PDF TEXT EXTRACTION ----------------
def extract_text_from_pdf(file_stream):

    text = ""

    try:
        file_stream.seek(0)   # ✅ IMPORTANT FIX

        with pdfplumber.open(file_stream) as pdf:
            for page in pdf.pages[:10]:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"

    except Exception as e:
        print("❌ PDF ERROR:", str(e))

    return text.strip()

# ---------------- AI QUESTION GENERATION ----------------
def generate_questions(text, types, count):

    short_text = text[:1200]

    types_desc = []

    if "mcq" in types:
        types_desc.append(f"Generate EXACTLY {count} MCQ questions")

    if "2mark" in types:
        types_desc.append(f"Generate EXACTLY {count} 2-mark questions")

    if "3mark" in types:
        types_desc.append(f"Generate EXACTLY {count} 3-mark questions")

    if "5mark" in types:
        types_desc.append(f"Generate EXACTLY {count} 5-mark questions")

    prompt = f"""
Return ONLY valid JSON.

{chr(10).join(types_desc)}

FORMAT:
{{
  "mcq": [],
  "two_mark": [],
  "three_mark": [],
  "five_mark": []
}}

TEXT:
{short_text}
"""

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            temperature=0.2,
            max_tokens=2500,
            messages=[{"role": "user", "content": prompt}]
        )

        raw = response.choices[0].message.content.strip()

        raw = raw.replace("```json", "").replace("```", "").strip()

        start = raw.find("{")
        end = raw.rfind("}")

        if start != -1 and end != -1:
            raw = raw[start:end + 1]

        parsed = json.loads(raw)

        parsed.setdefault("mcq", [])
        parsed.setdefault("two_mark", [])
        parsed.setdefault("three_mark", [])
        parsed.setdefault("five_mark", [])

        return parsed

    except Exception as e:
        print("❌ GENERATION ERROR:", str(e))

        return {
            "mcq": [],
            "two_mark": [],
            "three_mark": [],
            "five_mark": []
        }

# ---------------- HOME ----------------
@app.route("/")
def index():
    return render_template("index.html")

# ---------------- GENERATE ROUTE ----------------
@app.route("/generate", methods=["POST"])
def generate():

    try:
        if "pdf" not in request.files:
            return jsonify({"error": "No PDF uploaded"}), 400

        pdf_file = request.files["pdf"]

        if pdf_file.filename == "":
            return jsonify({"error": "No file selected"}), 400

        types = request.form.getlist("types")
        count = int(request.form.get("count", 5))

        if not types:
            return jsonify({"error": "No question types selected"}), 400

        # ✅ READ FILE FRESH EVERY TIME
        pdf_bytes = pdf_file.read()

        if not pdf_bytes:
            return jsonify({"error": "Empty PDF file"}), 400

        # ✅ CREATE NEW STREAM (VERY IMPORTANT)
        pdf_stream = io.BytesIO(pdf_bytes)
        pdf_stream.seek(0)

        text = extract_text_from_pdf(pdf_stream)

        print("📄 Extracted Text Length:", len(text))

        if len(text) < 50:
            return jsonify({"error": "PDF text too short"}), 400

        questions = generate_questions(text, types, count)

        return jsonify({
            "success": True,
            "data": questions
        })

    except Exception as e:
        print("🔥 SERVER ERROR:", str(e))

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# ---------------- DOWNLOAD TXT ----------------
@app.route("/download/txt", methods=["POST"])
def download_txt():

    data = request.json.get("data", {})

    text = json.dumps(data, indent=2)

    buf = io.BytesIO(text.encode())
    buf.seek(0)

    return send_file(buf, as_attachment=True, download_name="questions.txt")

# ---------------- DOWNLOAD PDF ----------------
@app.route("/download/pdf", methods=["POST"])
def download_pdf():

    data = request.json.get("data", {})

    buf = io.BytesIO()

    doc = SimpleDocTemplate(buf, pagesize=A4)
    styles = getSampleStyleSheet()

    story = []

    story.append(Paragraph("Exam Questions", styles["Heading1"]))

    for section, questions in data.items():

        if not isinstance(questions, list):
            continue

        story.append(Paragraph(section, styles["Heading2"]))

        for i, q in enumerate(questions, 1):
            story.append(Paragraph(f"Q{i}: {q.get('q', '')}", styles["Normal"]))
            story.append(Spacer(1, 10))

    doc.build(story)

    buf.seek(0)

    return send_file(buf, as_attachment=True, download_name="questions.pdf")

# ---------------- RUN ----------------
if __name__ == "__main__":

    port = int(os.environ.get("PORT", 8080))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=True
    )