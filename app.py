from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash, send_file, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_migrate import Migrate
from datetime import datetime, timedelta, timezone
import os
from dotenv import load_dotenv
from openai import OpenAI
import markdown
import json
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import PyPDF2  # Import PyPDF2 for PDF text extraction
import io
from PIL import Image, ImageDraw, ImageFont, ImageColor  # For PWA icon generation

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///learning.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
ALLOWED_EXTENSIONS = {'pdf'}

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Ensure static directories exist
os.makedirs(os.path.join('static', 'images'), exist_ok=True)
os.makedirs(os.path.join('static', 'js'), exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Initialize extensions
db = SQLAlchemy(app)
migrate = Migrate(app, db)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# Register markdown filter
@app.template_filter('markdown')
def render_markdown(text):
    if text:
        return markdown.markdown(text, extensions=['extra', 'nl2br', 'sane_lists'])
    return ""

# Register fromjson filter for parsing JSON strings
@app.template_filter('fromjson')
def parse_json(value):
    if value:
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return {}
    return {}

# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    syllabi = db.relationship('Syllabus', backref='user', lazy=True)
    assignments = db.relationship('Assignment', backref='user', lazy=True)
    todos = db.relationship('Todo', backref='user', lazy=True)
    study_plans = db.relationship('StudyPlan', backref='user', lazy=True)

class Syllabus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text)
    file_path = db.Column(db.String(255))  # Store the path to the uploaded PDF
    openai_file_id = db.Column(db.String(255))  # Store the OpenAI file ID
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.relationship('Note', backref='syllabus', lazy=True)

class Note(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    syllabus_id = db.Column(db.Integer, db.ForeignKey('syllabus.id'), nullable=False)
    topic = db.Column(db.String(200))
    subtopic = db.Column(db.String(200))
    order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey('assignment.id'), nullable=False)
    question_type = db.Column(db.String(20), nullable=False)  # multiple_choice, fill_blank, drag_drop, ordering, short_answer, long_answer
    question_text = db.Column(db.Text, nullable=False)
    options = db.Column(db.JSON)  # For multiple choice, drag and drop, and ordering questions
    correct_answer = db.Column(db.Text, nullable=False)
    points = db.Column(db.Integer, default=1)
    order = db.Column(db.Integer, default=0)  # For ordering questions
    topic = db.Column(db.String(200))
    subtopic = db.Column(db.String(200))
    explanation = db.Column(db.Text)

class Assignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    due_date = db.Column(db.DateTime, nullable=False)
    completed = db.Column(db.Boolean, default=False)
    student_answer = db.Column(db.Text)
    ai_feedback = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    syllabus_id = db.Column(db.Integer, db.ForeignKey('syllabus.id'), nullable=False)
    questions = db.relationship('Question', backref='assignment', lazy=True, order_by='Question.order')
    total_points = db.Column(db.Integer, default=0)
    earned_points = db.Column(db.Integer, default=0)

class Todo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    due_date = db.Column(db.DateTime)
    priority = db.Column(db.Integer, default=0)  # 0: Low, 1: Medium, 2: High
    completed = db.Column(db.Boolean, default=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class StudyPlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text)  # JSON content of the study plan
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
            return redirect(url_for('register'))
            
        if User.query.filter_by(email=email).first():
            flash('Email already registered', 'error')
            return redirect(url_for('register'))
            
        user = User(
            username=username,
            email=email,
            password=generate_password_hash(password)
        )
        
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful!', 'success')
        return redirect(url_for('login'))
        
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard'))
            
        flash('Invalid username or password', 'error')
        
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    # Get todos and assignments for the current user
    user_assignments = Assignment.query.filter_by(user_id=current_user.id).all()
    user_todos = Todo.query.filter_by(user_id=current_user.id).all()
    
    # Sort assignments for recent activity display
    recent_assignments = sorted(
        user_assignments, 
        key=lambda x: x.due_date if x.due_date else datetime.min, 
        reverse=True
    )[:5]
    
    return render_template(
        'dashboard.html', 
        assignments=user_assignments, 
        recent_assignments=recent_assignments,
        todos=user_todos
    )

@app.route('/chat')
@login_required
def chat_page():
    return render_template('chat.html')

@app.route('/chat', methods=['POST'])
@login_required
def chat():
    message = request.json.get('message')
    
    try:
        response = client.chat.completions.create(
            model="o4-mini",
            messages=[
                {"role": "system", "content": "You are a helpful educational assistant. Provide clear, concise explanations."},
                {"role": "user", "content": message}
            ]
        )
        return jsonify({"response": response.choices[0].message.content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/syllabi')
@login_required
def syllabi():
    user_syllabi = Syllabus.query.filter_by(user_id=current_user.id).all()
    return render_template('syllabi.html', syllabi=user_syllabi)

@app.route('/syllabi', methods=['POST'])
@login_required
def create_syllabus():
    if 'file' in request.files:
        file = request.files['file']
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{current_user.id}_{filename}")
            file.save(file_path)
            
            # Extract text directly from PDF using PyPDF2
            try:
                pdf_text = ""
                with open(file_path, 'rb') as pdf_file:
                    pdf_reader = PyPDF2.PdfReader(pdf_file)
                    for page_num in range(len(pdf_reader.pages)):
                        page = pdf_reader.pages[page_num]
                        pdf_text += page.extract_text() + "\n\n"
                
                # Use OpenAI to summarize and structure the extracted text
                response = client.chat.completions.create(
                    model="o4-mini",
                    messages=[
                        {"role": "system", "content": "Extract the main content from this PDF syllabus. Focus on the course objectives, topics, and requirements."},
                        {"role": "user", "content": pdf_text}
                    ]
                )
                content = response.choices[0].message.content
            except Exception as e:
                content = "Error extracting content from PDF"
                flash(f'Error processing PDF: {str(e)}', 'error')
            
            syllabus = Syllabus(
                title=request.form.get('title', filename),
                content=content,
                file_path=file_path,
                user_id=current_user.id,
                created_at=datetime.now(timezone.utc)
            )
        else:
            flash('Invalid file type. Only PDF files are allowed.', 'error')
            return redirect(url_for('syllabi'))
    else:
        # Handle text-only syllabus creation
        data = request.json
        syllabus = Syllabus(
            title=data['title'],
            content=data['content'],
            user_id=current_user.id,
            created_at=datetime.now(timezone.utc)
        )
    
    db.session.add(syllabus)
    db.session.commit()
    
    return jsonify({"message": "Syllabus created successfully"})

@app.route('/syllabi/<int:id>')
@login_required
def view_syllabus(id):
    syllabus = Syllabus.query.get_or_404(id)
    
    if syllabus.user_id != current_user.id:
        flash('Unauthorized access', 'error')
        return redirect(url_for('syllabi'))
        
    return render_template('view_syllabus.html', syllabus=syllabus)

@app.route('/syllabi/<int:id>/download')
@login_required
def download_syllabus(id):
    syllabus = Syllabus.query.get_or_404(id)
    if syllabus.user_id != current_user.id:
        flash('Unauthorized access', 'error')
        return redirect(url_for('syllabi'))
    
    if syllabus.file_path and os.path.exists(syllabus.file_path):
        return send_file(syllabus.file_path, as_attachment=True)
    else:
        flash('File not found', 'error')
        return redirect(url_for('view_syllabus', id=id))

@app.route('/syllabi/<int:id>/delete', methods=['DELETE'])
@login_required
def delete_syllabus(id):
    syllabus = Syllabus.query.get_or_404(id)
    
    if syllabus.user_id != current_user.id:
        return jsonify({"error": "Unauthorized"}), 403
    
    # Delete associated notes
    Note.query.filter_by(syllabus_id=syllabus.id).delete()
    
    # Delete associated assignments
    for assignment in Assignment.query.filter_by(syllabus_id=syllabus.id).all():
        # Delete questions for each assignment
        Question.query.filter_by(assignment_id=assignment.id).delete()
        db.session.delete(assignment)
    
    # Delete the OpenAI file if it exists
    if syllabus.openai_file_id:
        try:
            client.files.delete(file_id=syllabus.openai_file_id)
        except Exception as e:
            # Log the error but continue with database deletion
            print(f"Error deleting OpenAI file {syllabus.openai_file_id}: {e}")
    
    # Delete the physical file if it exists
    if syllabus.file_path and os.path.exists(syllabus.file_path):
        try:
            os.remove(syllabus.file_path)
        except Exception as e:
            # Log the error but continue with database deletion
            print(f"Error deleting file {syllabus.file_path}: {e}")
    
    # Delete the syllabus from the database
    db.session.delete(syllabus)
    db.session.commit()
    
    return jsonify({"message": "Syllabus deleted successfully"})

@app.route('/generate_notes', methods=['POST'])
@login_required
def generate_notes():
    syllabus_id = request.json.get('syllabus_id')
    syllabus = Syllabus.query.get_or_404(syllabus_id)
    
    if syllabus.user_id != current_user.id:
        return jsonify({"error": "Unauthorized"}), 403
    
    try:
        # Get syllabus content - from PDF if available
        syllabus_content = syllabus.content
        
        # If there's a PDF file, extract text directly to supplement the content
        if syllabus.file_path and os.path.exists(syllabus.file_path):
            try:
                pdf_text = ""
                with open(syllabus.file_path, 'rb') as pdf_file:
                    pdf_reader = PyPDF2.PdfReader(pdf_file)
                    for page_num in range(len(pdf_reader.pages)):
                        page = pdf_reader.pages[page_num]
                        pdf_text += page.extract_text() + "\n\n"
                
                # Combine existing content with PDF text
                syllabus_content = syllabus_content + "\n\nAdditional content from PDF:\n" + pdf_text
            except Exception as e:
                print(f"Error extracting text from PDF: {e}")
        
        # Generate structured notes with topics and subtopics
        response = client.chat.completions.create(
            model="o4-mini",
            messages=[
                {"role": "system", "content": """You are an expert educational content generator. Your task is to create comprehensive study notes.
                
                IMPORTANT: Your response MUST be valid JSON with this exact structure:
                {
                    "title": "Study Notes for [Course Name]",
                    "topics": [
                        {
                            "title": "Topic Title",
                            "subtopics": [
                                {
                                    "title": "Subtopic Title",
                                    "content": "Detailed notes content with markdown formatting",
                                    "key_points": ["Point 1", "Point 2", "Point 3"],
                                    "examples": ["Example 1", "Example 2"],
                                    "summary": "Brief summary of the subtopic"
                                }
                            ]
                        }
                    ]
                }
                
                Guidelines:
                1. Create 2-3 main topics based on the syllabus
                2. Each topic should have 2-3 subtopics
                3. Use markdown formatting for better readability
                4. Include key points, examples, and summaries for each subtopic
                5. Make notes engaging and easy to understand
                6. Use bullet points, lists, and headings for organization
                7. Include relevant examples and applications
                8. Add a brief summary at the end of each subtopic
                
                IMPORTANT: Your entire response must be ONLY valid JSON that can be parsed with json.loads(). 
                Do not include any explanations, markdown formatting outside of content fields, or other text."""},
                {"role": "user", "content": syllabus_content}
            ],
            response_format={"type": "json_object"}
        )
        
        # Get the content from the response
        content = response.choices[0].message.content
        print("Notes API Response:", content[:100] + "..." if len(content) > 100 else content)
        
        try:
            # Try to parse the JSON
            notes_data = json.loads(content)
        except json.JSONDecodeError as json_err:
            print(f"JSON parsing error: {json_err}")
            # Return an error response if JSON parsing fails
            return jsonify({"error": "Failed to generate structured notes. Please try again."}), 500
        
        # Create notes for each topic and subtopic
        note_order = 0
        for topic in notes_data['topics']:
            for subtopic in topic['subtopics']:
                note = Note(
                    title=f"{topic['title']}: {subtopic['title']}",
                    content=f"""# {subtopic['title']}

{subtopic['content']}

## Key Points
{chr(10).join(f"- {point}" for point in subtopic['key_points'])}

## Examples
{chr(10).join(f"- {example}" for example in subtopic['examples'])}

## Summary
{subtopic['summary']}""",
                    syllabus_id=syllabus_id,
                    topic=topic['title'],
                    subtopic=subtopic['title'],
                    order=note_order
                )
                db.session.add(note)
                note_order += 1
        
        db.session.commit()
        
        return jsonify({
            "message": "Notes generated successfully",
            "structure": notes_data
        })
    except Exception as e:
        print(f"Error generating notes: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/generate_assignment', methods=['POST'])
@login_required
def generate_assignment():
    syllabus_id = request.json.get('syllabus_id')
    syllabus = Syllabus.query.get_or_404(syllabus_id)
    
    if syllabus.user_id != current_user.id:
        return jsonify({"error": "Unauthorized"}), 403
    
    try:
        # Get syllabus content - from PDF if available
        syllabus_content = syllabus.content
        
        # If there's a PDF file, extract text directly to supplement the content
        if syllabus.file_path and os.path.exists(syllabus.file_path):
            try:
                pdf_text = ""
                with open(syllabus.file_path, 'rb') as pdf_file:
                    pdf_reader = PyPDF2.PdfReader(pdf_file)
                    for page_num in range(len(pdf_reader.pages)):
                        page = pdf_reader.pages[page_num]
                        pdf_text += page.extract_text() + "\n\n"
                
                # Combine existing content with PDF text
                syllabus_content = syllabus_content + "\n\nAdditional content from PDF:\n" + pdf_text
            except Exception as e:
                print(f"Error extracting text from PDF: {e}")
        
        # Generate structured assignment with topics and subtopics
        response = client.chat.completions.create(
            model="o4-mini",
            messages=[
                {"role": "system", "content": """You are an expert educational content generator. Your task is to create a comprehensive assignment.
                
                IMPORTANT: Your response MUST be valid JSON with this exact structure:
                {
                    "title": "Assignment Title",
                    "description": "Overall description",
                    "topics": [
                        {
                            "title": "Topic Title",
                            "subtopics": [
                                {
                                    "title": "Subtopic Title",
                                    "questions": [
                                        {
                                            "type": "multiple_choice",
                                            "text": "Question text",
                                            "options": ["Option 1", "Option 2", "Option 3", "Option 4"],
                                            "correct_answer": "Correct option",
                                            "points": 2,
                                            "explanation": "Explanation of the correct answer"
                                        },
                                        {
                                            "type": "fill_blank",
                                            "text": "Complete the sentence: The capital of France is _____.",
                                            "correct_answer": "Paris",
                                            "points": 1,
                                            "explanation": "Paris is the capital of France."
                                        },
                                        {
                                            "type": "ordering",
                                            "text": "Arrange these events in chronological order:",
                                            "options": ["Event 1", "Event 2", "Event 3", "Event 4"],
                                            "correct_answer": ["Event 1", "Event 2", "Event 3", "Event 4"],
                                            "points": 2,
                                            "explanation": "The correct chronological order is..."
                                        },
                                        {
                                            "type": "drag_drop",
                                            "text": "Match the following terms with their definitions:",
                                            "options": ["Term 1", "Term 2", "Term 3", "Term 4"],
                                            "correct_answer": ["Definition 1", "Definition 2", "Definition 3", "Definition 4"],
                                            "points": 2,
                                            "explanation": "The correct matches are..."
                                        },
                                        {
                                            "type": "short_answer",
                                            "text": "What is the main concept of...",
                                            "correct_answer": "Expected short answer",
                                            "points": 3,
                                            "explanation": "The main concept is..."
                                        },
                                        {
                                            "type": "long_answer",
                                            "text": "Explain in detail...",
                                            "correct_answer": "Expected detailed answer",
                                            "points": 5,
                                            "explanation": "A detailed explanation should include..."
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
                
                Guidelines:
                1. Create 2-3 main topics
                2. Each topic should have 2-3 subtopics
                3. Each subtopic should have 10 questions
                4. Mix different question types within each subtopic
                5. Ensure questions test understanding, not just memorization
                6. Include clear explanations for each answer
                7. Vary point values based on question complexity
                8. Make questions engaging and relevant to the syllabus content
                
                IMPORTANT: Your entire response must be ONLY valid JSON that can be parsed with json.loads(). 
                Do not include any explanations, markdown formatting, or other text."""},
                {"role": "user", "content": syllabus_content}
            ],
            response_format={"type": "json_object"}
        )
        
        # Get the content from the response
        content = response.choices[0].message.content
        print("Assignment API Response:", content[:100] + "..." if len(content) > 100 else content)
        
        try:
            # Try to parse the JSON
            assignment_data = json.loads(content)
        except json.JSONDecodeError as json_err:
            print(f"JSON parsing error: {json_err}")
            # Return an error response if JSON parsing fails
            return jsonify({"error": "Failed to generate structured assignment. Please try again."}), 500
        
        assignment = Assignment(
            title=assignment_data['title'],
            description=assignment_data['description'],
            due_date=datetime.now(timezone.utc) + timedelta(days=7),
            user_id=current_user.id,
            syllabus_id=syllabus_id
        )
        
        db.session.add(assignment)
        db.session.flush()  # Get the assignment ID
        
        # Add questions with their topics and subtopics
        question_order = 0
        for topic in assignment_data['topics']:
            for subtopic in topic['subtopics']:
                for q_data in subtopic['questions']:
                    question = Question(
                        assignment_id=assignment.id,
                        question_type=q_data['type'],
                        question_text=q_data['text'],
                        options=q_data.get('options'),
                        correct_answer=json.dumps(q_data['correct_answer']) if isinstance(q_data['correct_answer'], list) else q_data['correct_answer'],
                        points=q_data.get('points', 1),
                        order=question_order,
                        topic=topic['title'],
                        subtopic=subtopic['title'],
                        explanation=q_data.get('explanation', '')
                    )
                    db.session.add(question)
                    question_order += 1
        
        db.session.commit()
        
        return jsonify({
            "message": "Assignment created successfully",
            "id": assignment.id,
            "structure": assignment_data
        })
    except Exception as e:
        print(f"Error generating assignment: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/assignments')
@login_required
def assignments():
    user_assignments = Assignment.query.filter_by(user_id=current_user.id).all()
    now = datetime.now(timezone.utc)
    return render_template('assignments.html', assignments=user_assignments, now=now)

@app.route('/assignments/<int:id>')
@login_required
def view_assignment(id):
    assignment = Assignment.query.get_or_404(id)
    if assignment.user_id != current_user.id:
        flash('Unauthorized access', 'error')
        return redirect(url_for('assignments'))
    
    edit_mode = request.args.get('edit', '0') == '1'
    return render_template('view_assignment.html', assignment=assignment, edit_mode=edit_mode)

@app.route('/assignments/<int:id>/submit', methods=['POST'])
@login_required
def submit_assignment(id):
    assignment = Assignment.query.get_or_404(id)
    if assignment.user_id != current_user.id:
        return jsonify({"error": "Unauthorized"}), 403
    
    answers = request.json.get('answers', {})
    total_points = 0
    earned_points = 0
    feedback = []
    
    for question_id_str, answer in answers.items():
        question_id = int(question_id_str.replace('q', ''))
        question = Question.query.get(question_id)
        if not question:
            continue
            
        is_correct = False
        question_feedback = ""
        
        # Get the correct answer, converting from JSON string if needed
        correct_answer = question.correct_answer
        if question.question_type in ['ordering', 'drag_drop']:
            try:
                correct_answer = json.loads(correct_answer)
            except (json.JSONDecodeError, TypeError):
                pass  # Keep as string if not valid JSON
        
        if question.question_type == 'multiple_choice':
            # Simple string comparison
            is_correct = str(answer).strip() == str(correct_answer).strip()
            print(f"Multiple choice: Answer: '{answer}', Correct: '{correct_answer}', Match: {is_correct}")
        elif question.question_type == 'fill_blank':
            is_correct = str(answer).lower().strip() == str(correct_answer).lower().strip()
            print(f"Fill blank: Answer: '{answer}', Correct: '{correct_answer}', Match: {is_correct}")
        elif question.question_type == 'ordering':
            # Parse the answer if it's a JSON string
            try:
                student_answer = json.loads(answer) if isinstance(answer, str) else answer
                is_correct = student_answer == correct_answer
                # Store the parsed answer back into the answers dictionary
                answers[question_id_str] = json.dumps(student_answer)
                print(f"Ordering: Answer: {student_answer}, Correct: {correct_answer}, Match: {is_correct}")
            except (json.JSONDecodeError, TypeError) as e:
                print(f"Ordering parsing error: {e}")
                is_correct = False
        elif question.question_type == 'drag_drop':
            # Parse the answer if it's a JSON string
            try:
                student_answer = json.loads(answer) if isinstance(answer, str) else answer
                is_correct = student_answer == correct_answer
                # Store the parsed answer back into the answers dictionary
                answers[question_id_str] = json.dumps(student_answer)
                print(f"Drag drop: Answer: {student_answer}, Correct: {correct_answer}, Match: {is_correct}")
            except (json.JSONDecodeError, TypeError) as e:
                print(f"Drag drop parsing error: {e}")
                is_correct = False
        elif question.question_type in ['short_answer', 'long_answer']:
            # Use AI to evaluate the answer
            try:
                response = client.chat.completions.create(
                    model="o4-mini",
                    messages=[
                        {"role": "system", "content": f"""You are evaluating a {question.question_type} answer. 
                        Evaluate how well the student answer matches the expected answer.
                        
                        IMPORTANT: You must respond with ONLY a valid JSON object in the following format:
                        {{
                          "score": 0.85, // A number between 0 and 1 representing how correct the answer is
                          "feedback": "Your feedback to the student here"
                        }}
                        
                        Do not include any text before or after the JSON object.
                        The entire response must be a valid JSON object."""},
                        {"role": "user", "content": f"Question: {question.question_text}\nCorrect Answer: {correct_answer}\nStudent Answer: {answer}"}
                    ],
                    response_format={"type": "json_object"}
                )
                
                content = response.choices[0].message.content
                try:
                    evaluation = json.loads(content)
                    score = evaluation.get('score', 0)
                    is_correct = score >= 0.7
                    question_feedback = evaluation.get('feedback', "")
                    print(f"Essay: Score={score}, Is Correct={is_correct}, Feedback={question_feedback[:30]}...")
                except json.JSONDecodeError as json_err:
                    print(f"JSON decode error: {json_err} - Response content: {content}")
                    is_correct = False
                    question_feedback = "Error evaluating answer. Please try again."
            except Exception as e:
                print(f"Error evaluating answer: {str(e)}")
                question_feedback = "Error evaluating answer. Please try again."
                is_correct = False
        
        if is_correct:
            earned_points += question.points
        total_points += question.points
        
        # Ensure is_correct is a boolean, not a string or other value
        is_correct_bool = bool(is_correct)
        
        feedback.append({
            'question_id': question_id_str,
            'is_correct': is_correct_bool,
            'feedback': question_feedback
        })
        
        print(f"Question {question_id}: is_correct={is_correct_bool}, points={question.points if is_correct_bool else 0}")
    
    assignment.student_answer = json.dumps(answers)
    assignment.ai_feedback = json.dumps(feedback)
    assignment.completed = True
    assignment.total_points = total_points
    assignment.earned_points = earned_points
    
    db.session.commit()
    print({
        "message": "Assignment submitted successfully",
        "total_points": total_points,
        "earned_points": earned_points,
        "feedback": feedback
    })
    return jsonify({
        "message": "Assignment submitted successfully",
        "total_points": total_points,
        "earned_points": earned_points,
        "feedback": feedback
    })

@app.route('/todos')
@login_required
def todos():
    todos = Todo.query.filter_by(user_id=current_user.id).order_by(Todo.priority.desc(), Todo.due_date).all()
    return render_template('todos.html', todos=todos)

@app.route('/todos', methods=['POST'])
@login_required
def create_todo():
    data = request.get_json()
    todo = Todo(
        title=data['title'],
        description=data.get('description'),
        due_date=datetime.fromisoformat(data['due_date']),
        priority=data.get('priority', 0),
        user_id=current_user.id,
        created_at=datetime.now(timezone.utc)
    )
    db.session.add(todo)
    db.session.commit()
    return jsonify({'message': 'Todo created successfully', 'id': todo.id})

@app.route('/todos/<int:id>', methods=['PUT'])
@login_required
def update_todo(id):
    todo = Todo.query.get_or_404(id)
    if todo.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.get_json()
    if 'title' in data:
        todo.title = data['title']
    if 'description' in data:
        todo.description = data['description']
    if 'due_date' in data:
        todo.due_date = datetime.fromisoformat(data['due_date'])
    if 'priority' in data:
        todo.priority = data['priority']
    if 'completed' in data:
        todo.completed = data['completed']
    
    db.session.commit()
    return jsonify({'message': 'Todo updated successfully'})

@app.route('/todos/<int:id>', methods=['DELETE'])
@login_required
def delete_todo(id):
    todo = Todo.query.get_or_404(id)
    if todo.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    db.session.delete(todo)
    db.session.commit()
    return jsonify({'message': 'Todo deleted successfully'})

@app.route('/calendar')
@login_required
def calendar():
    # Get todos and assignments for the current user
    todos = Todo.query.filter_by(user_id=current_user.id).all()
    assignments = Assignment.query.filter_by(user_id=current_user.id).all()
    
    # Convert todos and assignments to calendar events
    events = []
    
    # Add todos
    for todo in todos:
        events.append({
            'id': f'todo-{todo.id}',
            'title': todo.title,
            'start': todo.due_date.isoformat() if todo.due_date else None,
            'end': todo.due_date.isoformat() if todo.due_date else None,
            'extendedProps': {
                'type': 'todo',
                'description': todo.description,
                'completed': todo.completed,
                'priority': todo.priority
            }
        })
    
    # Add assignments
    for assignment in assignments:
        events.append({
            'id': f'assignment-{assignment.id}',
            'title': assignment.title,
            'start': assignment.due_date.isoformat() if assignment.due_date else None,
            'end': assignment.due_date.isoformat() if assignment.due_date else None,
            'extendedProps': {
                'type': 'assignment',
                'description': assignment.description,
                'completed': bool(assignment.student_answer),
                'syllabus_id': assignment.syllabus_id
            }
        })
    
    return render_template('calendar.html', events=events)

@app.route('/study-plans')
@login_required
def study_plans():
    user_plans = StudyPlan.query.filter_by(user_id=current_user.id).order_by(StudyPlan.created_at.desc()).all()
    return render_template('study_plans.html', plans=user_plans)

@app.route('/study-plans/<int:id>')
@login_required
def view_study_plan(id):
    plan = StudyPlan.query.get_or_404(id)
    if plan.user_id != current_user.id:
        flash('Unauthorized access', 'error')
        return redirect(url_for('study_plans'))
    
    return render_template('view_study_plan.html', plan=plan)

@app.route('/generate-study-plan', methods=['POST'])
@login_required
def generate_study_plan():
    data = request.json
    start_date = datetime.fromisoformat(data.get('start_date'))
    end_date = datetime.fromisoformat(data.get('end_date'))
    
    # Get all user's syllabi, assignments, and todos
    syllabi = Syllabus.query.filter_by(user_id=current_user.id).all()
    assignments = Assignment.query.filter_by(user_id=current_user.id).all()
    todos = Todo.query.filter_by(user_id=current_user.id, completed=False).all()
    
    if not syllabi:
        return jsonify({"error": "You need at least one syllabus to generate a study plan"}), 400
    
    # Prepare data for OpenAI
    syllabi_data = []
    for syllabus in syllabi:
        notes = Note.query.filter_by(syllabus_id=syllabus.id).all()
        topics = {}
        for note in notes:
            if note.topic not in topics:
                topics[note.topic] = []
            topics[note.topic].append(note.subtopic)
        
        syllabus_assignments = [a for a in assignments if a.syllabus_id == syllabus.id]
        
        syllabi_data.append({
            "id": syllabus.id,
            "title": syllabus.title,
            "topics": topics,
            "assignments": [{"id": a.id, "title": a.title, "due_date": a.due_date.isoformat() if a.due_date else None} for a in syllabus_assignments]
        })
    
    # Get days between start and end date
    days_count = (end_date - start_date).days + 1
    
    try:
        # Generate study plan with OpenAI
        response = client.chat.completions.create(
            model="o4-mini",
            messages=[
                {"role": "system", "content": """You are an expert academic planner. Your task is to create a comprehensive study plan based on the user's syllabi, assignments, and todos.
                
                IMPORTANT: Your response MUST be valid JSON with this exact structure:
                {
                    "title": "Study Plan Title",
                    "days": [
                        {
                            "date": "YYYY-MM-DD",
                            "sessions": [
                                {
                                    "start_time": "HH:MM",
                                    "end_time": "HH:MM",
                                    "activity_type": "study", // or "assignment", "break", "review"
                                    "title": "Session Title",
                                    "description": "Detailed description of the study session",
                                    "syllabus_id": 1, // optional, only for study activities
                                    "assignment_id": 2, // optional, only for assignment activities
                                    "todo_id": 3 // optional, only for todo activities
                                }
                            ]
                        }
                    ]
                }
                
                Guidelines:
                1. Create a balanced study plan across all syllabi
                2. Schedule time for assignments based on their due dates
                3. Include regular breaks (15-30 minutes)
                4. Mix study sessions between different subjects to improve retention
                5. Include review sessions for previously studied material
                6. Plan for 3-5 study sessions per day, each 1-2 hours long
                7. Leave some free time each day
                8. Prioritize assignments with closer due dates
                9. Consider the complexity of topics when allocating time
                
                IMPORTANT: Your entire response must be ONLY valid JSON that can be parsed with json.loads().
                Do not include any explanations, markdown formatting, or other text."""},
                {"role": "user", "content": json.dumps({
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "days_count": days_count,
                    "syllabi": syllabi_data,
                    "todos": [{"id": t.id, "title": t.title, "priority": t.priority, "due_date": t.due_date.isoformat() if t.due_date else None} for t in todos]
                })}
            ],
            response_format={"type": "json_object"}
        )
        
        # Get the content from the response
        content = response.choices[0].message.content
        
        try:
            # Try to parse the JSON
            plan_data = json.loads(content)
        except json.JSONDecodeError as json_err:
            print(f"JSON parsing error: {json_err}")
            return jsonify({"error": "Failed to generate study plan. Please try again."}), 500
        
        # Create the study plan
        plan = StudyPlan(
            title=plan_data['title'],
            start_date=start_date,
            end_date=end_date,
            user_id=current_user.id,
            content=content,
            created_at=datetime.now(timezone.utc)
        )
        
        db.session.add(plan)
        db.session.commit()
        
        return jsonify({
            "message": "Study plan generated successfully",
            "id": plan.id,
            "plan": plan_data
        })
    except Exception as e:
        print(f"Error generating study plan: {str(e)}")
        return jsonify({"error": str(e)}), 500

# PWA service worker route
@app.route('/service-worker.js')
def service_worker():
    return send_from_directory('static/js', 'service-worker.js')

# PWA offline route
@app.route('/offline')
def offline():
    return render_template('offline.html')

# PWA icon routes
@app.route('/static/images/<icon>')
def serve_pwa_icon(icon):
    # Check if the icon is already created
    icon_path = os.path.join('static', 'images', icon)
    if os.path.exists(icon_path):
        return send_file(icon_path)
    
    # Parse icon name to determine size
    if icon.startswith('icon-'):
        try:
            sizes = icon.replace('icon-', '').replace('.png', '').split('x')
            width = int(sizes[0])
            height = int(sizes[1]) if len(sizes) > 1 else width
        except (ValueError, IndexError):
            width = height = 512
    elif icon.startswith('favicon-'):
        try:
            width = height = int(icon.replace('favicon-', '').replace('.png', '').split('x')[0])
        except (ValueError, IndexError):
            width = height = 32
    else:
        width = height = 512
    
    # Create a simple colored icon with text
    img = Image.new('RGBA', (width, height), color=(79, 70, 229, 255))  # Indigo color
    
    # Add text to the icon
    if width >= 64:  # Only add text for larger icons
        draw = ImageDraw.Draw(img)
        text = "AI"
        
        # Estimate font size based on image width
        font_size = width // 3
        try:
            # Try to use a system font
            font = ImageFont.truetype("arial.ttf", font_size)
        except IOError:
            # Fallback to default font
            font = ImageFont.load_default()
        
        # Calculate text position to center it
        text_width, text_height = draw.textsize(text, font=font) if hasattr(draw, 'textsize') else (font_size * len(text) * 0.6, font_size)
        position = ((width - text_width) / 2, (height - text_height) / 2)
        
        # Draw the text
        draw.text(position, text, fill=(255, 255, 255, 255), font=font)
    
    # Save the icon
    os.makedirs(os.path.dirname(icon_path), exist_ok=True)
    img.save(icon_path, format="PNG")
    
    return send_file(icon_path)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, use_reloader=False) 