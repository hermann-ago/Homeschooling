from fpdf import FPDF

class PDF(FPDF):
    pass

pdf = PDF()
pdf.add_page()
pdf.set_font("Arial", size=15)
pdf.cell(200, 10, txt="Homeschool Curriculum - Science Grade 4", ln=1, align="C")
pdf.set_font("Arial", size=12)
pdf.cell(200, 10, txt="Chapter 1: The Solar System - Planets and orbits.", ln=1, align="L")
pdf.cell(200, 10, txt="Chapter 2: Ecosystems - How animals and plants interact.", ln=1, align="L")
pdf.cell(200, 10, txt="Chapter 3: Weather & Climate - Understanding rain, snow, and heat.", ln=1, align="L")
pdf.output("dummy_curriculum.pdf")
print("PDF created successfully.")
