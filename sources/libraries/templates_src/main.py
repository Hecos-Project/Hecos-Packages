"""
MODULE: Templates Plugin — Main Entry Point
DESCRIPTION: Exposes TemplateTools to the Hecos agent loop.
             Allows the LLM to discover and render templates.
"""

from __future__ import annotations
import json
from typing import Optional

from .store import list_templates, render_template

class TemplateTools:
    """
    Hecos Templates Plugin — find and render message templates.
    """

    def __init__(self):
        self.tag    = "TEMPLATES"
        self.desc   = "Find and render predefined templates for emails and messages."
        self.status = "ONLINE"

    def list_templates(self, channel: Optional[str] = None) -> str:
        """
        List all available templates.
        :param channel: Optional channel filter (e.g. 'whatsapp', 'email', 'telegram', 'discord').
        """
        all_tpls = list_templates(channel=channel)
        if not all_tpls:
            return "❌ Nessun template trovato."
        
        lines = ["📝 **Template Disponibili:**"]
        for t in all_tpls:
            default_marker = " [DEFAULT]" if t.get("is_default") else ""
            vars_str = ", ".join(t.get("variables", []))
            lines.append(f"- ID: {t['id']} | Nome: {t['name']} | Canale: {t['channel']}{default_marker}")
            if vars_str:
                lines.append(f"  Variabili richieste: {vars_str}")
            if t.get("description"):
                lines.append(f"  Desc: {t['description']}")
            
        return "\n".join(lines)

    def render_template(self, template_id_or_name: str, variables: str) -> str:
        """
        Render a template by replacing its variables and combining header/body/footer.
        Use this before sending a message if you want to use a specific template.
        :param template_id_or_name: The ID or the exact Name of the template.
        :param variables: A JSON string containing the variables to inject (e.g. '{"nome": "Mario"}').
        """
        all_tpls = list_templates()
        
        # Find template by ID or exact Name (case-insensitive)
        target = None
        for t in all_tpls:
            if t["id"] == template_id_or_name or t["name"].lower() == template_id_or_name.lower():
                target = t
                break

        # Fuzzy match: all words of the query appear in the template name
        if not target:
            query_words = template_id_or_name.lower().split()
            for t in all_tpls:
                tname = t["name"].lower()
                if all(w in tname for w in query_words):
                    target = t
                    break

        # Substring match
        if not target:
            q = template_id_or_name.lower()
            for t in all_tpls:
                if q in t["name"].lower():
                    target = t
                    break
                
        if not target:
            return f"❌ Template '{template_id_or_name}' non trovato."
            
        try:
            vars_dict = json.loads(variables) if variables else {}
        except json.JSONDecodeError:
            return "❌ Errore nel parse JSON delle variabili."
            
        rendered = render_template(target["id"], vars_dict)
        
        if target["channel"] == "email":
            return f"OGGETTO: {rendered.get('subject', '')}\n\n{rendered.get('body_text', '')}"
        
        # Messenger channels
        parts = []
        if rendered.get("header"):
            parts.append(rendered["header"])
        if rendered.get("body_text"):
            parts.append(rendered["body_text"])
        if rendered.get("footer"):
        return "\n\n".join(parts)

    def create_template(self, name: str, body_html: str, subject: str = "", description: str = "") -> str:
        """
        Create a new custom template with raw HTML and CSS. 
        You can use Jinja placeholders like {{ title }} or {{ image }} inside the HTML.
        :param name: Human readable name for the template.
        :param body_html: The raw HTML content (including inline CSS).
        :param subject: The email subject (can also contain placeholders).
        :param description: Brief description of the template purpose.
        """
        from .store import save_template
        data = {
            "name": name,
            "channel": "email",
            "body_html": body_html,
            "subject": subject,
            "description": description
        }
        try:
            result = save_template(data)
            return f"✅ Template creato con successo. ID: {result['id']}"
        except Exception as e:
            return f"❌ Errore durante la creazione del template: {str(e)}"

    def update_template(self, template_id: str, body_html: str) -> str:
        """
        Update the HTML body of an existing template.
        :param template_id: The ID of the template to update.
        :param body_html: The new raw HTML content.
        """
        from .store import save_template, get_template
        existing = get_template(template_id)
        if not existing:
            return f"❌ Errore: Template {template_id} non trovato."
            
        data = {
            "id": template_id,
            "name": existing.get("name", "Custom Template"),
            "channel": existing.get("channel", "email"),
            "body_html": body_html
        }
        try:
            result = save_template(data)
            return f"✅ Template aggiornato con successo. ID: {result['id']}"
        except Exception as e:
            return f"❌ Errore durante l'aggiornamento del template: {str(e)}"

