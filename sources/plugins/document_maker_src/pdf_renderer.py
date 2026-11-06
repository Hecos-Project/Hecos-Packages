import os
from hecos.core.logging import logger


def generate_pdf_from_html(final_html: str, pdf_output_path: str, layout: dict) -> str:
    """Generates a PDF from HTML using Playwright. Returns path or error string."""
    try:
        from hecos.modules.browser_automation.plugin import engine
    except ImportError:
        return generate_pdf_fallback(final_html, pdf_output_path, layout)

    def _pdf_task():
        if not engine._state.get("browser") or not engine._state["browser"].is_connected():
            from playwright.sync_api import sync_playwright
            if not engine._state.get("pw_instance"):
                engine._state["pw_instance"] = sync_playwright().start()
            engine._state["browser"] = engine._state["pw_instance"].chromium.launch(headless=True)
        
        browser = engine._state["browser"]
        context = browser.new_context()
        page = context.new_page()
        
        try:
            import tempfile
            temp_html_path = None
            with tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode="w", encoding="utf-8") as tmp:
                tmp.write(final_html)
                temp_html_path = tmp.name

            file_url = "file:///" + os.path.normpath(temp_html_path).replace("\\", "/")
            page.goto(file_url, wait_until="networkidle")
            page.pdf(
                path=pdf_output_path, 
                format=layout.get("page_format", "A4"), 
                print_background=True, 
                margin={
                    "top": f"{layout.get('margin_top', 20)}mm", 
                    "right": f"{layout.get('margin_right', 20)}mm", 
                    "bottom": f"{layout.get('margin_bottom', 20)}mm", 
                    "left": f"{layout.get('margin_left', 20)}mm"
                }
            )
        finally:
            if temp_html_path and os.path.exists(temp_html_path):
                try:
                    os.remove(temp_html_path)
                except Exception as e:
                    logger.error(f"[DOCS] Failed to delete temp HTML: {e}")
            page.close()
            context.close()
        return pdf_output_path

    try:
        result_path = engine._run_on_browser_thread(_pdf_task)
        if result_path and os.path.exists(result_path):
            return result_path
        else:
            logger.warning(f"[DOCS] Playwright returned path but file not found: {result_path}")
            return None
    except Exception as e:
        logger.error(f"[DOCS] Playwright PDF generation failed: {e}")
        return None


def generate_pdf_fallback(final_html: str, pdf_output_path: str, layout: dict) -> str:
    """Tries standalone Playwright when browser_automation module is unavailable."""
    try:
        from playwright.sync_api import sync_playwright
        import tempfile

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            
            temp_html_path = None
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode="w", encoding="utf-8") as tmp:
                    tmp.write(final_html)
                    temp_html_path = tmp.name

                file_url = "file:///" + os.path.normpath(temp_html_path).replace("\\", "/")
                page.goto(file_url, wait_until="networkidle")
                page.pdf(
                    path=pdf_output_path, 
                    format=layout.get("page_format", "A4"), 
                    print_background=True, 
                    margin={
                        "top": f"{layout.get('margin_top', 20)}mm", 
                        "right": f"{layout.get('margin_right', 20)}mm", 
                        "bottom": f"{layout.get('margin_bottom', 20)}mm", 
                        "left": f"{layout.get('margin_left', 20)}mm"
                    }
                )
            finally:
                if temp_html_path and os.path.exists(temp_html_path):
                    try:
                        os.remove(temp_html_path)
                    except Exception:
                        pass
                page.close()
                context.close()
                browser.close()

        if os.path.exists(pdf_output_path):
            return pdf_output_path
        return None
    except ImportError:
        logger.error("[DOCS] Playwright is not installed. PDF generation unavailable. "
                     "Install with: pip install playwright && python -m playwright install chromium")
        return None
    except Exception as e:
        logger.error(f"[DOCS] Standalone Playwright PDF failed: {e}")
        return None


def calculate_layout_issues(file_path: str) -> str:
    """
    Calculates page breaks for a document and returns a report of elements split across pages.
    """
    from hecos.core.modules import engine
    if not engine.get_module("browser_automation"):
        return "Error: browser_automation module is required for layout optimization."
        
    def _optimization_task():
        if not engine._state.get("browser") or not engine._state["browser"].is_connected():
            from playwright.sync_api import sync_playwright
            if not engine._state.get("pw_instance"):
                engine._state["pw_instance"] = sync_playwright().start()
            engine._state["browser"] = engine._state["pw_instance"].chromium.launch(headless=True)
        
        browser = engine._state["browser"]
        context = browser.new_context()
        page = context.new_page()
        
        try:
            file_url = "file:///" + os.path.normpath(file_path).replace("\\", "/")
            page.goto(file_url, wait_until="networkidle")
            
            issues = page.evaluate('''() => {
                const pageHeight = 1122.5; // A4 height at 96 DPI
                const elements = document.querySelectorAll('h1, h2, h3, img, p, div.card, div.photo-card, div.gallery');
                const issues = [];
                elements.forEach((el, index) => {
                    const rect = el.getBoundingClientRect();
                    const top = rect.top + window.scrollY;
                    const bottom = rect.bottom + window.scrollY;
                    
                    const startPage = Math.floor(top / pageHeight);
                    const endPage = Math.floor(bottom / pageHeight);
                    
                    if (startPage !== endPage && bottom - top > 0) {
                        let snippet = el.outerHTML;
                        if (snippet.length > 80) snippet = snippet.substring(0, 80) + '...';
                        issues.push(`Pagina ${startPage+1}->${endPage+1}: Elemento tagliato a meta -> ${snippet}`);
                    } else if (endPage > startPage && top % pageHeight > pageHeight - 80 && el.tagName.match(/^H[1-6]/)) {
                        issues.push(`Pagina ${startPage+1}: Titolo isolato a fine pagina -> ${el.textContent.substring(0,40)}`);
                    }
                });
                return issues;
            }''')
            return issues
        except Exception as e:
            logger.error(f"[DOCS] Layout optimization failed: {e}")
            return [f"Error calculating layout: {str(e)}"]
        finally:
            page.close()
            context.close()
            
    issues = engine._run_on_browser_thread(_optimization_task)
    if not issues:
        return "✅ L'impaginazione sembra corretta, non ci sono elementi importanti tagliati a metà."
    
    report = "⚠️ ATTENZIONE: Sono stati rilevati i seguenti errori di impaginazione:\n\n"
    for issue in issues:
        report += f"- {issue}\n"
    report += "\nUsa `DOCS__modify_document` per inserire `<div style=\"page-break-before: always;\"></div>` prima degli elementi tagliati."
    return report
