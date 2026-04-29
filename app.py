import json
import os
import io
import pdfplumber

from flask import Flask, render_template, request, jsonify, send_file
from groq import Groq

from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

from dotenv import load_dotenv

# ---------------- LOAD ENV ----------------
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

        file_stream.seek(0)

        with pdfplumber.open(file_stream) as pdf:

            max_pages = min(len(pdf.pages), 20)

            for i in range(max_pages):

                page = pdf.pages[i]

                page_text = page.extract_text()

                if page_text:
                    text += page_text + "\n"

    except Exception as e:
        print("❌ PDF EXTRACTION ERROR:", str(e))

    return text.strip()

# ---------------- AI QUESTION GENERATION ----------------
def generate_questions(text, types, count):

    short_text = text[:12000]

    type_prompt = []

    if "mcq" in types:
        type_prompt.append(f"{count} MCQ questions")

    if "2mark" in types:
        type_prompt.append(f"{count} short 2-mark questions")

    if "3mark" in types:
        type_prompt.append(f"{count} medium 3-mark questions")

    if "5mark" in types:
        type_prompt.append(f"{count} long 5-mark questions")

    prompt = f"""
Generate exam questions from the provided study material.

Generate:
{chr(10).join(type_prompt)}

Return ONLY valid JSON.

FORMAT:

{{
  "mcq": [
    {{
      "question": "Sample question",
      "options": [
        "Option A",
        "Option B",
        "Option C",
        "Option D"
      ]
    }}
  ],

  "two_mark": [
    {{
      "question": "Sample 2 mark question"
    }}
  ],

  "three_mark": [
    {{
      "question": "Sample 3 mark question"
    }}
  ],

  "five_mark": [
    {{
      "question": "Sample 5 mark question"
    }}
  ]
}}

STUDY MATERIAL:
{short_text}
"""

    try:

        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            temperature=0.3,
            max_tokens=3000,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        raw = response.choices[0].message.content.strip()

        print("RAW AI RESPONSE:")
        print(raw)

        # Remove markdown formatting
        raw = raw.replace("```json", "")
        raw = raw.replace("```", "")
        raw = raw.strip()

        # Extract JSON safely
        start = raw.find("{")
        end = raw.rfind("}")

        if start != -1 and end != -1:
            raw = raw[start:end + 1]

        parsed = json.loads(raw)

        # Safety defaults
        parsed.setdefault("mcq", [])
        parsed.setdefault("two_mark", [])
        parsed.setdefault("three_mark", [])
        parsed.setdefault("five_mark", [])

        return parsed

    except Exception as e:

        print("❌ AI GENERATION ERROR:", str(e))

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

# ---------------- GENERATE QUESTIONS ----------------
@app.route("/generate", methods=["POST"])
def generate():

    try:

        # ---------------- CHECK PDF ----------------
        if "pdf" not in request.files:
            return jsonify({
                "success": False,
                "error": "No PDF uploaded"
            }), 400

        pdf_file = request.files["pdf"]

        if pdf_file.filename == "":
            return jsonify({
                "success": False,
                "error": "No file selected"
            }), 400

        # ---------------- FORM DATA ----------------
        types = request.form.getlist("types")
        count = int(request.form.get("count", 5))

        if not types:
            return jsonify({
                "success": False,
                "error": "No question types selected"
            }), 400

        # ---------------- READ PDF ----------------
        pdf_bytes = pdf_file.read()

        if not pdf_bytes:
            return jsonify({
                "success": False,
                "error": "Uploaded PDF is empty"
            }), 400

        pdf_stream = io.BytesIO(pdf_bytes)

        text = extract_text_from_pdf(pdf_stream)

        print("📄 Extracted Text Length:", len(text))

        if len(text.strip()) < 50:
            return jsonify({
                "success": False,
                "error": "No readable text found in PDF"
            }), 400

        # ---------------- GENERATE ----------------
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

    try:

        data = request.json.get("data", {})

        text = json.dumps(data, indent=2)

        buffer = io.BytesIO()

        buffer.write(text.encode("utf-8"))

        buffer.seek(0)

        return send_file(
            buffer,
            as_attachment=True,
            download_name="questions.txt",
            mimetype="text/plain"
        )

    except Exception as e:

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# ---------------- DOWNLOAD PDF ----------------
@app.route("/download/pdf", methods=["POST"])
def download_pdf():

    try:

        data = request.json.get("data", {})

        buffer = io.BytesIO()

        doc = SimpleDocTemplate(buffer, pagesize=A4)

        styles = getSampleStyleSheet()

        story = []

        story.append(
            Paragraph("Generated Exam Questions", styles["Heading1"])
        )

        section_names = {
            "mcq": "MCQ Questions",
            "two_mark": "2-Mark Questions",
            "three_mark": "3-Mark Questions",
            "five_mark": "5-Mark Questions"
        }

        for key, title in section_names.items():

            questions = data.get(key, [])

            if not questions:
                continue

            story.append(
                Spacer(1, 12)
            )

            story.append(
                Paragraph(title, styles["Heading2"])
            )

            for i, q in enumerate(questions, 1):

                question_text = q.get("question", "")

                story.append(
                    Paragraph(
                        f"<b>Q{i}:</b> {question_text}",
                        styles["Normal"]
                    )
                )

                # MCQ options
                if "options" in q:

                    options = q["options"]

                    for idx, opt in enumerate(options):

                        option_letter = chr(65 + idx)

                        story.append(
                            Paragraph(
                                f"{option_letter}. {opt}",
                                styles["Normal"]
                            )
                        )

                story.append(
                    Spacer(1, 10)
                )

        doc.build(story)

        buffer.seek(0)

        return send_file(
            buffer,
            as_attachment=True,
            download_name="questions.pdf",
            mimetype="application/pdf"
        )

    except Exception as e:

        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# ---------------- RUN APP ----------------
if __name__ == "__main__":

    port = int(os.environ.get("PORT", 8080))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=True
    )