import json
import os

from flask import Blueprint, jsonify, request
from openai import OpenAI
from src.models.note import Note, db

note_bp = Blueprint('note', __name__)

@note_bp.route('/notes/translate', methods=['POST'])
def translate_note():
    """Translate a note title and content using OpenRouter."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'A JSON request body is required'}), 400

    title = data.get('title')
    content = data.get('content')
    target_language = data.get('target_language')
    if not all(isinstance(value, str) for value in (title, content, target_language)):
        return jsonify({'error': 'Title, content, and target language are required'}), 400
    if not target_language.strip():
        return jsonify({'error': 'Target language is required'}), 400

    api_key = os.getenv('OPEN_ROUTER_KEY')
    if not api_key:
        return jsonify({'error': 'Translation is not configured on the server'}), 503

    prompt_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        'prompts',
        'translate_prompt.md'
    )

    try:
        with open(prompt_path, encoding='utf-8') as prompt_file:
            system_prompt = prompt_file.read().replace('{target_language}', target_language.strip())

        client = OpenAI(
            base_url='https://openrouter.ai/api/v1',
            api_key=api_key
        )
        response = client.chat.completions.create(
            model='deepseek/deepseek-chat',  # OpenAI/Google models are geo-blocked on OpenRouter here
            response_format={'type': 'json_object'},
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': json.dumps({'title': title, 'content': content}, ensure_ascii=False)}
            ]
        )

        translated = json.loads(response.choices[0].message.content)
        if not isinstance(translated, dict) or not all(
            isinstance(translated.get(field), str) for field in ('title', 'content')
        ):
            return jsonify({'error': 'Translation service returned an invalid response'}), 502

        return jsonify({'title': translated['title'], 'content': translated['content']})
    except Exception:
        from flask import current_app
        current_app.logger.exception('Translation request failed')
        return jsonify({'error': 'Translation failed. Please try again.'}), 502

@note_bp.route('/notes', methods=['GET'])
def get_notes():
    """Get all notes, ordered by most recently updated"""
    notes = Note.query.order_by(Note.updated_at.desc()).all()
    return jsonify([note.to_dict() for note in notes])

@note_bp.route('/notes', methods=['POST'])
def create_note():
    """Create a new note"""
    try:
        data = request.json
        if not data or 'title' not in data or 'content' not in data:
            return jsonify({'error': 'Title and content are required'}), 400
        
        note = Note(title=data['title'], content=data['content'])
        db.session.add(note)
        db.session.commit()
        return jsonify(note.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@note_bp.route('/notes/<int:note_id>', methods=['GET'])
def get_note(note_id):
    """Get a specific note by ID"""
    note = Note.query.get_or_404(note_id)
    return jsonify(note.to_dict())

@note_bp.route('/notes/<int:note_id>', methods=['PUT'])
def update_note(note_id):
    """Update a specific note"""
    try:
        note = Note.query.get_or_404(note_id)
        data = request.json
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        note.title = data.get('title', note.title)
        note.content = data.get('content', note.content)
        db.session.commit()
        return jsonify(note.to_dict())
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@note_bp.route('/notes/<int:note_id>', methods=['DELETE'])
def delete_note(note_id):
    """Delete a specific note"""
    try:
        note = Note.query.get_or_404(note_id)
        db.session.delete(note)
        db.session.commit()
        return '', 204
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@note_bp.route('/notes/search', methods=['GET'])
def search_notes():
    """Search notes by title or content"""
    query = request.args.get('q', '')
    if not query:
        return jsonify([])
    
    notes = Note.query.filter(
        (Note.title.contains(query)) | (Note.content.contains(query))
    ).order_by(Note.updated_at.desc()).all()
    
    return jsonify([note.to_dict() for note in notes])

