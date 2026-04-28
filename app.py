import json
import os
import pdfplumber
from flask import Flask, render_template, request, jsonify, send_file
from groq import Groq
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import io

app = Flask(__name__)

# ---------------- API KEY ----------------
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

print("GROQ KEY LOADED:", bool(GROQ_API_KEY))

if not GROQ_API_KEY:
    print("❌ ERROR: GROQ_API_KEY is missing!")

client = Groq(api_key=GROQ_API_KEY)


# ---------------- PDF TEXT ----------------
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


# ---------------- AI GENERATION ----------------
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
Generate exam questions from this text.

{chr(10).join(types_desc)}

Return ONLY VALID JSON in this exact format:
{{
  "mcq":[{{"q":"","a":"","b":"","c":"","d":"","ans":"A"}}],
  "two_mark":[{{"q":""}}],
  "three_mark":[{{"q":""}}],
  "five_mark":[{{"q":""}}]
}}

TEXT:
{text[:4000]}
"""

    try:
        response = client.chat.completions.create(
            model="llama3-8b-8192",
            max_tokens=1500,
            temperature=0.5,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        raw = response.choices[0].message.content

        print("✅ RAW AI RESPONSE:")
        print(raw)

        clean = raw.replace("```json", "").replace("```", "").strip()

        try:
            parsed = json.loads(clean)
            return parsed

        except Exception as json_error:

            print("❌ JSON PARSE ERROR:", str(json_error))
            print("RAW OUTPUT:", raw)

            return {
                "mcq": [],
                "two_mark": [],
                "three_mark": [],
                "five_mark": [],
                "debug": "JSON parse failed"
            }

    except Exception as e:

        print("❌ GROQ ERROR:", str(e))

        return {
            "mcq": [],
            "two_mark": [],
            "three_mark": [],
            "five_mark": [],
            "error": str(e)
        }


# ---------------- HOME ----------------
@app.route("/")
def index():
    return render_template("index.html")


# ---------------- GENERATE ----------------
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

        text = extract_text_from_pdf(pdf_file.stream)

        print("📄 Extracted Text Length:", len(text))

        if len(text) < 100:
            return jsonify({"error": "PDF text too short"}), 400

        questions = generate_questions(text, types, count)

        return jsonify({
            "success": True,
            "data": questions
        })

    except Exception as e:

        print("🔥 SERVER ERROR:", str(e))

        return jsonify({
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

    doc = SimpleDocTemplate(buf, pagesize=A4)

    styles = getSampleStyleSheet()

    story = []

    story.append(Paragraph("Exam Questions", styles["Heading1"]))

    for section, questions in data.items():

        story.append(Paragraph(section, styles["Heading2"]))

        for i, q in enumerate(questions, 1):

            story.append(
                Paragraph(
                    f"Q{i}: {q.get('q', '')}",
                    styles["Normal"]
                )
            )

            story.append(Spacer(1, 10))

    doc.build(story)

    buf.seek(0)

    return send_file(
        buf,
        as_attachment=True,
        download_name="questions.pdf"
    )


# ---------------- RUN ----------------
if __name__ == "__main__":

    port = int(os.environ.get("PORT", 8080))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=True
    )