import os
from hecos.core.logging import logger


def resolve_document_path(file_path: str, output_dir: str) -> str:
    """Resolves a document path — accepts absolute paths, relative names, or partial matches."""
    if os.path.isabs(file_path) and os.path.exists(file_path):
        return file_path

    if not file_path.endswith((".html", ".pdf")):
        file_path_html = file_path + ".html"
    else:
        file_path_html = file_path

    exact = os.path.join(output_dir, os.path.basename(file_path_html))
    if os.path.exists(exact):
        return exact

    search_term = os.path.basename(file_path).replace(".html", "").replace(".pdf", "").lower()
    if os.path.isdir(output_dir):
        for f in os.listdir(output_dir):
            if search_term in f.lower() and f.endswith(".html"):
                return os.path.join(output_dir, f)

    return None


def op_add_images(html: str, content: str, target_selector: str) -> str:
    """Adds images to the document. content is HTML with <img> tags."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")

        if target_selector:
            for element in soup.find_all(string=lambda text: text and target_selector in text):
                new_content = BeautifulSoup(content, "html.parser")
                element.replace_with(new_content)
            return str(soup)

        gallery = (
            soup.select_one(".gallery") or
            soup.select_one(".photo-gallery") or
            soup.select_one(".photo-grid") or
            soup.select_one("main") or
            soup.find("body")
        )
        if gallery:
            new_content = BeautifulSoup(content, "html.parser")
            gallery.append(new_content)
        
        return str(soup)
    except ImportError:
        return op_append(html, content)


def op_replace_section(html: str, content: str, selector: str) -> str:
    """Replaces the first element matching the CSS selector with new content."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        target = soup.select_one(selector)
        if target:
            new_content = BeautifulSoup(content, "html.parser")
            target.replace_with(new_content)
            return str(soup)
        else:
            logger.warning(f"[DOCS] CSS selector '{selector}' not found in document.")
            return html
    except ImportError:
        return html


def op_change_layout(html: str, css_content: str) -> str:
    """Injects CSS rules into the document's <style> block."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        
        style_tag = soup.find("style")
        if style_tag:
            style_tag.string = (style_tag.string or "") + "\n/* --- Layout Override --- */\n" + css_content
        else:
            head = soup.find("head")
            if not head:
                head = soup.new_tag("head")
                if soup.html:
                    soup.html.insert(0, head)
            new_style = soup.new_tag("style")
            new_style.string = css_content
            head.append(new_style)
        
        return str(soup)
    except ImportError:
        if "</head>" in html:
            return html.replace("</head>", f"<style>\n{css_content}\n</style>\n</head>")
        return f"<style>\n{css_content}\n</style>\n" + html


def op_append(html: str, content: str) -> str:
    """Appends content before </body>."""
    if "</body>" in html:
        return html.replace("</body>", f"\n{content}\n</body>")
    return html + f"\n{content}"


def modify_document_content(original_html: str, operation: str, content: str, target_selector: str = ""):
    """
    Applies operation to document content. Returns (modified_html, error_message).
    """
    operation = operation.lower().strip()
    if operation == "add_images":
        return op_add_images(original_html, content, target_selector), None

    elif operation == "replace_section":
        if not target_selector:
            return None, "Error: replace_section requires target_selector (CSS selector to find the element to replace)."
        return op_replace_section(original_html, content, target_selector), None

    elif operation == "change_layout":
        return op_change_layout(original_html, content), None

    elif operation == "append":
        return op_append(original_html, content), None

    elif operation == "patch":
        if not target_selector:
            return None, "Error: patch requires target_selector (the exact text to find and replace)."
        if target_selector not in original_html:
            preview = original_html[:400].replace('\n', '↵')
            return None, f"Error: Text to replace not found in document. File starts with: {preview}..."
        return original_html.replace(target_selector, content, 1), None

    else:
        return None, f"Error: Unknown operation '{operation}'. Use: add_images, replace_section, change_layout, append, or patch."
