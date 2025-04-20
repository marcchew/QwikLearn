# QwikLearn

An intelligent learning platform powered by AI. The platform provides AI-generated assignments, study notes, study plans, and personalized learning support.

## Features

- AI-generated assignments based on syllabus
- Automated assignment follow-ups
- AI-powered explanations for answers
- Well-formatted study notes with tables and images
- Interactive chatbot for learning support
- Syllabus-based content organization

## Setup

1. Clone the repository
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Create a `.env` file with your OpenAI API key:
   ```
   OPENAI_API_KEY=your_api_key_here
   SECRET_KEY=your_secret_key_here
   ```
5. Initialize the database:
   ```bash
   flask db init
   flask db migrate
   flask db upgrade
   ```
6. Run the application:
   ```bash
   flask run
   ```

## Usage

1. Register an account
2. Upload your syllabus
3. Access AI-generated content and assignments
4. Use the chatbot for additional support

## Technology Stack

- Backend: Flask
- Database: SQLAlchemy
- AI: OpenAI
- Frontend: HTML, CSS, JavaScript 