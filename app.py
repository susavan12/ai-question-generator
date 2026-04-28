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


# ---------------- SAFE JSON EXTRACTION ----------------
def extract_json(raw):

    raw = raw.replace("```json", "")
    raw = raw.replace("```", "")
    raw = raw.strip()

    start = raw.find("{")
    end = raw.rfind("}")

    if start != -1 and end != -1:
        raw = raw[start:end + 1]

    return json.loads(raw)


# ---------------- AI QUESTION GENERATION ----------------
def generate_questions(text, types, count):

    result = {
        "mcq": [],
        "two_mark": [],
        "three_mark": [],
        "five_mark": []
    }

    short_text = text[:2500]

    try:

        # ---------- MCQ ----------
        if "mcq" in types:

            prompt = f"""
Generate EXACTLY {count} MCQ questions from the text.

Return ONLY JSON.

FORMAT:
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
  ]
}}

TEXT:
{short_text}
"""

            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                temperature=0.3,
                max_tokens=2500,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )

            raw = response.choices[0].message.content

            parsed = extract_json(raw)

            result["mcq"] = parsed.get("mcq", [])


        # ---------- 2 MARK ----------
        if "2mark" in types:

            prompt = f"""
Generate EXACTLY {count} short 2-mark questions from the text.

Return ONLY JSON.

FORMAT:
{{
  "two_mark": [
    {{
      "q": "question"
    }}
  ]
}}

TEXT:
{short_text}
"""

            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                temperature=0.3,
                max_tokens=1500,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )

            raw = response.choices[0].message.content

            parsed = extract_json(raw)

            result["two_mark"] = parsed.get("two_mark", [])


        # ---------- 3 MARK ----------
        if "3mark" in types:

            prompt = f"""
Generate EXACTLY {count} descriptive 3-mark questions from the text.

Return ONLY JSON.

FORMAT:
{{
  "three_mark": [
    {{
      "q": "question"
    }}
  ]
}}

TEXT:
{short_text}
"""

            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                temperature=0.3,
                max_tokens=1500,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )

            raw = response.choices[0].message.content

            parsed = extract_json(raw)

            result["three_mark"] = parsed.get("three_mark", [])


        # ---------- 5 MARK ----------
        if "5mark" in types:

            prompt = f"""
Generate EXACTLY {count} long 5-mark questions from the text.

Return ONLY JSON.

FORMAT:
{{
  "five_mark": [
    {{
      "q": "question"
    }}
  ]
}}

TEXT:
{short_text}
"""

            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                temperature=0.3,
                max_tokens=2000,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )

            raw = response.choices[0].message.content

            parsed = extract_json(raw)

            result["five_mark"] = parsed.get("five_mark", [])


        return result

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