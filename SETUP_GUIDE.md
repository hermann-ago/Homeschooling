# Homeschooling App - Hosting Setup Guide

This guide will help you set up and host the Homeschooling application on a secondary device (like an old laptop) connected to your home network.

## 1. Prerequisites

Before starting, ensure the hosting laptop has the following installed:

- **Git**: [Download here](https://git-scm.com/downloads)
- **Python (3.10 or higher)**: [Download here](https://www.python.org/downloads/)
- **Node.js (LTS version)**: [Download here](https://nodejs.org/)

## 2. Initial Setup

Open a terminal (PowerShell or Command Prompt) on the laptop and follow these steps:

### Clone the Repository
You don't need to create a folder manually. Git will create one for you.
```bash
git clone https://github.com/hermann-ago/Homeschooling.git
cd Homeschooling
```

### Backend Configuration
1. Navigate to the backend directory:
   ```bash
   cd backend
   ```
2. Create a virtual environment:
   ```bash
   python -m venv venv
   ```
3. Activate the virtual environment:
   - **Windows**: `.\venv\Scripts\activate`
   - **Mac/Linux**: `source venv/bin/activate`
4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
5. Create your `.env` file (copy your Gemini API key here):
   ```bash
   notepad .env
   ```

### Frontend Configuration
1. Go back to the project root, then into the frontend:
   ```bash
   cd ../frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```

## 3. Running the App

To start the server, go back to the project root and run the master script:

```bash
cd ..
python run_app.py
```

## 4. Accessing the App

Once the script is running, it will display a **Network URL** (e.g., `http://192.168.1.15:5173`).

- **On the laptop**: Open `http://localhost:5173`
- **On other devices (phone/tablet/PC)**: Open the Network URL displayed in the terminal.

---

> [!TIP]
> Keep the terminal window open while you want to use the app. If you close it, the server will stop.
