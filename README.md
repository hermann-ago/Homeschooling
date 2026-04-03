# Homeschooling - Private Learning Management System

A beautiful, local-first web application designed for homeschool families to manage multiple children's curricula, schedules, and daily progress.

## ✨ Features

- **Daily Canvas**: Interactive daily dashboard with PDF viewing, cross-book inserts, and AI-powered learning tools (quizzes, summaries, key terms, logic simplification).
- **Scheduler**: Automated, balanced scheduling across multiple children and subjects.
- **Progress Tracking**: Real-time visualization of curriculum completion and family-wide status.
- **Curriculum Management**: PDF-based text analysis and TOC extraction for easy material organization.

## 🚀 Quick Start

1. **Prerequisites**:
   *   Python 3.10+
   *   Node.js 18+

2. **Environment Setup**:
   *   Add your `GEMINI_API_KEY` to the **Settings** page in the app (UI) or create a `backend/.env` file.

3. **Run the Application**:
   Execute the root-level runner script:
   ```bash
   python run_app.py
   ```
   This will start both the FastAPI backend (port 8000) and the Vite frontend (port 5173).

## 📁 Project Structure

*   `backend/`: FastAPI + SQLAlchemy + SQLite
    *   `models/`: Database schema, organized by domain.
    *   `routers/`: API endpoints, organized by feature.
    *   `services/`: Business logic, AI integration, and PDF parsing.
    *   `schemas/`: Pydantic models for request/response validation.
    *   `dev/`: Local development tools and test fixtures.
*   `frontend/`: React + Tailwind CSS + Vite
    *   `src/pages/`: Main application views.
    *   `src/components/`: Reusable UI components.
    *   `src/api/`: Frontend API client modules.
    *   `src/hooks/`: Custom React hooks.
*   `run_app.py`: Integrated development server runner.

## 🛠 Tech Stack

- **Frontend**: React, Lucide Icons, Date-fns, Tailwind CSS.
- **Backend**: FastAPI, SQLAlchemy (ORM), Alembic (Migrations), SQLite.
- **AI**: Google Gemini Pro & Flash (via LangChain/Google AI SDK).
