import json
import os
import io
import pdfplumber

from flask import Flask, render_template, request, jsonify, send_file
from groq import Groq

from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet


app = Flask(__name__)


# ---------------- API KEY ----------------
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

print("GROQ KEY LOADED:", bool(GROQ_API_KEY))

if not GROQ_API_KEY:
    print("❌ ERROR: GROQ_API_KEY is missing!")

client = Groq(api_key=GROQ_API_KEY)


# ---------------- TEST ROUTE ----------------
@app.route("/test-groq")
def test_groq():

    try:

        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "user",
                    "content": "Say hello"
                }
            ]
        )

        return jsonify({
            "success": True,
            "response": response.choices[0].message.content
        })

    except Exception as e:

        print("❌ TEST GROQ ERROR:", str(e))

        return jsonify({
            "success": False,
            "error": str(e)
        })


# ---------------- PDF TEXT EXTRACTION ----------------
def extract_text_from_pdf(file_stream):

    text = ""

    try:

        with pdfplumber.open(file_stream) as pdf:

            for page in pdf.pages[:20]:

                page_text = page.extract_text()

                if page_text:
                    text += page_text + "\n"

    except Exception as e:

        print("❌ PDF ERROR:", str(e))

    return text.strip()


# ---------------- AI QUESTION GENERATION ----------------
def generate_questions(text, types, count):

    types_desc = []

    if "mcq" in types:
        types_desc.append(f"{count} MCQ questions with 4 options A B C D")

    if "2mark" in types:
        types_desc.append(f"{count} 2-mark short questions")

    if "3mark" in types:
        types_desc.append(f"{count} 3-mark descriptive questions")

    if "5mark" in types:
        types_desc.append(f"{count} 5-mark long questions")

    prompt = f"""
You are an exam paper generator.

Generate questions ONLY from the given text.

{chr(10).join(types_desc)}

IMPORTANT:
Return ONLY pure JSON.
Do not write explanation.
Do not use markdown.
Do not use ```json

JSON FORMAT:

{{
  "mcq": [
    {{
      "q": "question",
      "a": "option A",
      "b": "option B",
      "c": "option C",
      "d": "option D",
      "ans": "A"
    }}
  ],
  "two_mark": [
    {{
      "q": "question"
    }}
  ],
  "three_mark": [
    {{
      "q": "question"
    }}
  ],
  "five_mark": [
    {{
      "q": "question"
    }}
  ]
}}

TEXT:
{text[:2000]}
"""

    try:

        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            temperature=0.2,
            max_tokens=4000,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        raw = response.choices[0].message.content.strip()

        print("========== RAW RESPONSE ==========")
        print(raw)
        print("==================================")

        clean = raw.replace("```json", "")
        clean = clean.replace("```", "")
        clean = clean.strip()

        start = clean.find("{")
        end = clean.rfind("}")

        if start != -1 and end != -1:
            clean = clean[start:end+1]

        parsed = json.loads(clean)

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
            "five_mark": [],
            "error": str(e)
        }


# ---------------- HOME PAGE ----------------
@app.route("/")
def index():
    return render_template("index.html")


# ---------------- GENERATE ROUTE ----------------
@app.route("/generate", methods=["POST"])
def generate():

    try:

        if "pdf" not in request.files:
            return jsonify({
                "error": "No PDF uploaded"
            }), 400

        pdf_file = request.files["pdf"]

        if pdf_file.filename == "":
            return jsonify({
                "error": "No file selected"
            }), 400

        types = request.form.getlist("types")

        count = int(request.form.get("count", 5))

        # SAFETY LIMIT
        if count > 7:
            count = 7

        if not types:
            return jsonify({
                "error": "No question types selected"
            }), 400

        text = extract_text_from_pdf(pdf_file.stream)

        print("📄 Extracted Text Length:", len(text))

        if len(text) < 100:
            return jsonify({
                "error": "PDF text too short"
            }), 400

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

    return send_file(
        buf,
        as_attachment=True,
        download_name="questions.txt"
    )


# ---------------- DOWNLOAD PDF ----------------
@app.route("/download/pdf", methods=["POST"])
def download_pdf():

    data = request.json.get("data", {})

    buf = io.BytesIO()

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4
    )

    styles = getSampleStyleSheet()

    story = []

    story.append(
        Paragraph(
            "Exam Questions",
            styles["Heading1"]
        )
    )

    for section, questions in data.items():

        if not isinstance(questions, list):
            continue

        story.append(
            Paragraph(
                section,
                styles["Heading2"]
            )
        )

        for i, q in enumerate(questions, 1):

            story.append(
                Paragraph(
                    f"Q{i}: {q.get('q', '')}",
                    styles["Normal"]
                )
            )

            story.append(
                Spacer(1, 10)
            )

    doc.build(story)

    buf.seek(0)

    return send_file(
        buf,
        as_attachment=True,
        download_name="questions.pdf"
    )


# ---------------- RUN APP ----------------
if __name__ == "__main__":

    port = int(os.environ.get("PORT", 8080))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=True
    )