import json
import os
import pdfplumber
from flask import Flask, render_template, request, jsonify, send_file
from groq import Groq
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
import io

# ---------------- APP INIT ----------------
app = Flask(__name__)

# Safe API key load
GROQ_KEY = os.environ.get("GROQ_API_KEY")

if not GROQ_KEY:
    print("❌ GROQ_API_KEY NOT FOUND")
else:
    print("✅ GROQ KEY LOADED")

client = Groq(api_key=GROQ_KEY)

# ---------------- HEALTH CHECK (IMPORTANT) ----------------
@app.route("/health")
def health():
    return "OK", 200

# ---------------- HOME ROUTE (SAFE VERSION) ----------------
@app.route("/")
def index():
    try:
        return render_template("index.html")
    except Exception as e:
        print("Template error:", e)
        return "Server is running", 200


# ---------------- PDF TEXT EXTRACTION ----------------
def extract_text_from_pdf(file_stream):
    text = ""
    with pdfplumber.open(file_stream) as pdf:
        for page in pdf.pages[:20]:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text.strip()


# ---------------- QUESTION GENERATION ----------------
def generate_questions(text, types, count):
    types_desc = []

    if "mcq" in types:
        types_desc.append(f"{count} MCQ questions with 4 options A B C D (one correct)")
    if "2mark" in types:
        types_desc.append(f"{count} 2-mark short questions")
    if "3mark" in types:
        types_desc.append(f"{count} 3-mark questions")
    if "5mark" in types:
        types_desc.append(f"{count} 5-mark long questions")

    prompt = f"""
Generate exam questions based ONLY on the text.

GENERATE:
{chr(10).join(types_desc)}

Return JSON ONLY:
{{
"mcq":[{{"q":"","a":"","b":"","c":"","d":"","ans":"A"}}],
"two_mark":[{{"q":""}}],
"three_mark":[{{"q":""}}],
"five_mark":[{{"q":""}}]
}}

TEXT:
{text[:5000]}
"""

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )

        raw = response.choices[0].message.content
        clean = raw.replace("```json", "").replace("```", "").strip()

        return json.loads(clean)

    except Exception as e:
        print("Groq Error:", e)
        raise Exception("AI generation failed")


# ---------------- GENERATE API ----------------
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

        text = extract_text_from_pdf(pdf_file.stream)

        if len(text) < 50:
            return jsonify({"error": "PDF text too small"}), 400

        questions = generate_questions(text, types, count)

        return jsonify({"success": True, "data": questions})

    except Exception as e:
        print("ERROR:", e)
        return jsonify({"error": str(e)}), 500


# ---------------- DOWNLOAD TXT ----------------
@app.route("/download/txt", methods=["POST"])
def download_txt():
    data = request.json.get("data", {})

    lines = ["EXAM PAPER", "="*40]

    for section in ["mcq", "two_mark", "three_mark", "five_mark"]:
        for i, q in enumerate(data.get(section, []), 1):
            lines.append(f"Q{i}. {q.get('q')}")

    buf = io.BytesIO("\n".join(lines).encode("utf-8"))
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

    for section in ["mcq", "two_mark", "three_mark", "five_mark"]:
        for i, q in enumerate(data.get(section, []), 1):
            story.append(Paragraph(f"Q{i}. {q.get('q')}", styles["Normal"]))
            story.append(Spacer(1, 10))

    doc.build(story)
    buf.seek(0)

    return send_file(buf, as_attachment=True, download_name="questions.pdf")


# ---------------- RUN (LOCAL ONLY) ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)