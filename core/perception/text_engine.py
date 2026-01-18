"""
UI Automation Text Engine Module.

This module provides functionality to extract text and structure from Windows
applications using Microsoft UI Automation API via the uiautomation library.

Handles the "Phantom Windows" problem where windows may close between
event capture and processing.
"""

import logging
from typing import Optional, Dict, Any, List
import json

# Try to import uiautomation - if not available, the module will still load
# but extract_context will return None
try:
    import uiautomation as uia
    UIA_AVAILABLE = True
except ImportError:
    UIA_AVAILABLE = False
    uia = None

# Win32 API for checking if window exists
try:
    import win32gui
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False
    win32gui = None

logger = logging.getLogger(__name__)


class TextEngine:
    """
    Extracts text and UI structure from Windows applications.
    
    Uses Microsoft UI Automation API to access the Accessibility Tree.
    Implements Phantom Window detection to handle closed windows gracefully.
    """
    
    def __init__(self, max_depth: int = 5, max_elements: int = 500):
        """
        Initialize the TextEngine.
        
        Args:
            max_depth: Maximum depth to traverse the UI tree.
            max_elements: Maximum number of UI elements to extract.
        """
        self.max_depth = max_depth
        self.max_elements = max_elements
        
        if not UIA_AVAILABLE:
            logger.warning(
                "uiautomation library not available. "
                "TextEngine will not be able to extract UI context. "
                "Install with: pip install uiautomation"
            )
        
        if not WIN32_AVAILABLE:
            logger.warning(
                "win32gui library not available. "
                "Phantom Window detection will not work. "
                "Install with: pip install pywin32"
            )
        
        logger.info("TextEngine initialized (UIA: %s, Win32: %s)", 
                    UIA_AVAILABLE, WIN32_AVAILABLE)
    
    def _is_window_alive(self, hwnd: int) -> bool:
        """
        Check if a window with the given HWND still exists.
        
        This implements the Phantom Window detection.
        
        Args:
            hwnd: Window handle to check.
            
        Returns:
            True if the window exists, False otherwise.
        """
        if not WIN32_AVAILABLE:
            # If win32gui is not available, assume window is alive
            # This may cause errors but won't crash the system
            return True
        
        try:
            return win32gui.IsWindow(hwnd)
        except Exception as e:
            logger.debug("Error checking window existence: %s", e)
            return False
    
    def _extract_element_info(self, element, depth: int = 0) -> Optional[Dict[str, Any]]:
        """
        Extract information from a UI Automation element.
        
        Args:
            element: UI Automation element.
            depth: Current depth in the tree.
            
        Returns:
            Dictionary with element info or None if max depth exceeded.
        """
        if depth > self.max_depth:
            return None
        
        try:
            info = {
                'control_type': element.ControlTypeName if hasattr(element, 'ControlTypeName') else 'Unknown',
                'name': element.Name if hasattr(element, 'Name') else '',
                'value': element.GetLegacyIAccessiblePattern().Value if hasattr(element, 'GetLegacyIAccessiblePattern') else '',
                'class_name': element.ClassName if hasattr(element, 'ClassName') else '',
                'automation_id': element.AutomationId if hasattr(element, 'AutomationId') else '',
            }
            
            # Only include non-empty values to reduce noise
            if not info['name']:
                del info['name']
            if not info['value']:
                del info['value']
            if not info['class_name']:
                del info['class_name']
            if not info['automation_id']:
                del info['automation_id']
            
            return info
            
        except Exception as e:
            logger.debug("Error extracting element info: %s", e)
            return None
    
    def _traverse_tree(self, element, depth: int = 0, 
                       count: int = 0) -> List[Dict[str, Any]]:
        """
        Traverse the UI Automation tree and extract element information.
        
        Args:
            element: Root UI Automation element.
            depth: Current depth in the tree.
            count: Number of elements extracted so far.
            
        Returns:
            List of element information dictionaries.
        """
        if depth > self.max_depth or count >= self.max_elements:
            return []
        
        elements = []
        
        # Extract current element info
        info = self._extract_element_info(element, depth)
        if info:
            elements.append(info)
            count += 1
        
        # Traverse children
        try:
            walker = uia.GetTreeWalker()
            child = walker.GetFirstChildChild(element)
            
            while child and count < self.max_elements:
                child_info = self._extract_element_info(child, depth + 1)
                if child_info:
                    elements.append(child_info)
                    count += 1
                
                # Recursively traverse grandchildren
                grandchildren = self._traverse_tree(child, depth + 2, count)
                elements.extend(grandchildren)
                count += len(grandchildren)
                
                child = walker.GetNextSiblingChild(child)
                
        except Exception as e:
            logger.debug("Error traversing tree: %s", e)
        
        return elements
    
    def extract_context(self, hwnd: int) -> Optional[Dict[str, Any]]:
        """
        Extract UI context from a window.
        
        This method implements the Phantom Window check. If the window
        no longer exists, it returns None to allow fallback to OCR.
        
        Args:
            hwnd: Window handle (HWND) of the target window.
            
        Returns:
            Dictionary with UI context information, or None if:
            - Window doesn't exist (Phantom Window)
            - uiautomation is not available
            - Error during extraction
        """
        if not UIA_AVAILABLE:
            logger.debug("uiautomation not available, cannot extract context")
            return None
        
        # Check for Phantom Window
        if not self._is_window_alive(hwnd):
            logger.debug("Phantom Window detected: HWND %d no longer exists", hwnd)
            return None
        
        try:
            # Get the window element from HWND
            control = uia.ControlFromHandle(hwnd)
            if not control:
                logger.debug("Could not get control from HWND %d", hwnd)
                return None
            
            # Extract window title
            window_title = control.Name if hasattr(control, 'Name') else ''
            
            # Traverse the UI tree
            elements = self._traverse_tree(control)
            
            # Build the context result
            context = {
                'hwnd': hwnd,
                'title': window_title,
                'elements_count': len(elements),
                'elements': elements,
            }
            
            logger.debug("Extracted context from HWND %d: %d elements", 
                        hwnd, len(elements))
            
            return context
            
        except Exception as e:
            logger.error("Error extracting context from HWND %d: %s", hwnd, e)
            return None
    
    def extract_text_from_context(self, context: Dict[str, Any]) -> str:
        """
        Extract all text from a UI context dictionary.
        
        Args:
            context: Context dictionary from extract_context().
            
        Returns:
            Concatenated text from all UI elements.
        """
        if not context:
            return ''
        
        text_parts = []
        
        # Add window title
        if 'title' in context and context['title']:
            text_parts.append(context['title'])
        
        # Add text from elements
        for element in context.get('elements', []):
            if 'name' in element and element['name']:
                text_parts.append(element['name'])
            if 'value' in element and element['value']:
                text_parts.append(element['value'])
        
        return ' '.join(text_parts)
    
    def extract_context_to_json(self, hwnd: int) -> Optional[str]:
        """
        Extract UI context and return as JSON string.
        
        Args:
            hwnd: Window handle (HWND) of the target window.
            
        Returns:
            JSON string with UI context, or None on error.
        """
        context = self.extract_context(hwnd)
        if context is None:
            return None
        
        try:
            return json.dumps(context, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("Error serializing context to JSON: %s", e)
            return None


# Singleton instance for easy import
_text_engine_instance = None


def get_text_engine() -> TextEngine:
    """Get or create the singleton TextEngine instance."""
    global _text_engine_instance
    if _text_engine_instance is None:
        _text_engine_instance = TextEngine()
    return _text_engine_instance
