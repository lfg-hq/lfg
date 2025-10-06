"""
AI integration functions for codebase-aware feature development
"""

import logging
from typing import Dict, Any, Optional, List
from django.contrib.auth.models import User
from projects.models import Project

from .retrieval import ContextualCodeRetriever, ArchitecturalPatternDetector


logger = logging.getLogger(__name__)


def get_codebase_context_for_prd(project_id: str, 
                                project_description: str, 
                                features: List[str], 
                                user: Optional[User] = None) -> str:
    """
    Get codebase context for PRD generation
    
    Args:
        project_id: Project UUID
        project_description: High-level project description
        features: List of feature descriptions
        user: User requesting the context
        
    Returns:
        Formatted context string for AI PRD generation
    """
    try:
        # Get project
        project = Project.objects.get(project_id=project_id)
        
        # Initialize retriever
        retriever = ContextualCodeRetriever(project, user)
        
        # Get context for PRD generation
        context = retriever.get_context_for_prd_generation(project_description, features)
        
        # Add architectural pattern analysis
        pattern_detector = ArchitecturalPatternDetector(project)
        patterns = pattern_detector.detect_patterns()
        
        if patterns:
            context += "\n\n## Detected Architectural Patterns\n"
            
            for pattern_name, pattern_info in patterns.items():
                if pattern_info.get('detected'):
                    confidence = pattern_info.get('confidence', 0)
                    context += f"- **{pattern_name.replace('_', ' ').title()}**: "
                    context += f"Confidence {confidence:.1%}"
                    
                    if 'instances' in pattern_info:
                        context += f" ({pattern_info['instances']} instances)"
                    context += "\n"
        
        return context
        
    except Project.DoesNotExist:
        return f"No codebase context available - project {project_id} not found."
    except Exception as e:
        logger.error(f"Error getting codebase context: {e}")
        return f"Error analyzing codebase: {str(e)}"


def get_codebase_context_for_feature(project_id: str, 
                                   feature_description: str,
                                   user: Optional[User] = None) -> Dict[str, Any]:
    """
    Get detailed codebase context for a specific feature request
    
    Args:
        project_id: Project UUID
        feature_description: Description of the feature to implement
        user: User requesting the context
        
    Returns:
        Dictionary with context, suggestions, and metadata
    """
    try:
        # Get project
        project = Project.objects.get(project_id=project_id)
        
        # Initialize retriever
        retriever = ContextualCodeRetriever(project, user)
        
        # Get context for feature
        context_result = retriever.get_context_for_feature_request(feature_description)
        
        return context_result
        
    except Project.DoesNotExist:
        return {
            'context': f"Project {project_id} not found",
            'suggestions': [],
            'relevant_files': [],
            'error': 'Project not found'
        }
    except Exception as e:
        logger.error(f"Error getting feature context: {e}")
        return {
            'context': f"Error analyzing codebase: {str(e)}",
            'suggestions': [],
            'relevant_files': [],
            'error': str(e)
        }


def search_similar_implementations(project_id: str, 
                                 functionality: str,
                                 user: Optional[User] = None) -> List[Dict[str, Any]]:
    """
    Search for existing implementations of similar functionality
    
    Args:
        project_id: Project UUID
        functionality: Description of functionality to search for
        user: User performing the search
        
    Returns:
        List of similar implementations found
    """
    try:
        # Get project
        project = Project.objects.get(project_id=project_id)
        
        # Initialize retriever
        retriever = ContextualCodeRetriever(project, user)
        
        # Search for implementations
        implementations = retriever.search_existing_implementations(functionality)
        
        return implementations
        
    except Project.DoesNotExist:
        logger.error(f"Project {project_id} not found")
        return []
    except Exception as e:
        logger.error(f"Error searching implementations: {e}")
        return []


def enhance_ticket_with_codebase_context(project_id: str, 
                                       ticket_description: str,
                                       user: Optional[User] = None) -> Dict[str, Any]:
    """
    Enhance a ticket/task description with relevant codebase context
    
    Args:
        project_id: Project UUID  
        ticket_description: Original ticket description
        user: User creating the ticket
        
    Returns:
        Enhanced ticket information with codebase context
    """
    try:
        # Get project
        project = Project.objects.get(project_id=project_id)
        
        # Get contextual information
        retriever = ContextualCodeRetriever(project, user)
        context_result = retriever.get_context_for_feature_request(ticket_description)
        
        if context_result.get('error'):
            return {
                'enhanced_description': ticket_description,
                'context': context_result['context'],
                'suggestions': [],
                'affected_files': [],
                'complexity_estimate': 'medium',
                'error': context_result['error']
            }
        
        # Enhance ticket description
        enhanced_description = _enhance_ticket_description(
            ticket_description,
            context_result['suggestions'],
            context_result['relevant_files']
        )
        
        # Estimate complexity based on similar code
        complexity_estimate = _estimate_ticket_complexity(
            context_result['relevant_files'],
            context_result['suggestions']
        )
        
        # Extract affected files
        affected_files = [
            {
                'path': file_info['path'],
                'language': file_info['language'],
                'functions': file_info['functions'][:5],  # Limit to 5 functions
                'reason': 'Contains similar functionality'
            }
            for file_info in context_result['relevant_files'][:8]
        ]
        
        return {
            'enhanced_description': enhanced_description,
            'context': context_result['context'],
            'suggestions': context_result['suggestions'],
            'affected_files': affected_files,
            'complexity_estimate': complexity_estimate,
            'error': None
        }
        
    except Project.DoesNotExist:
        return {
            'enhanced_description': ticket_description,
            'context': f"Project {project_id} not found",
            'suggestions': [],
            'affected_files': [],
            'complexity_estimate': 'medium',
            'error': 'Project not found'
        }
    except Exception as e:
        logger.error(f"Error enhancing ticket: {e}")
        return {
            'enhanced_description': ticket_description,
            'context': f"Error analyzing codebase: {str(e)}",
            'suggestions': [],
            'affected_files': [],
            'complexity_estimate': 'medium',
            'error': str(e)
        }


def _enhance_ticket_description(description: str, 
                              suggestions: List[Dict[str, str]], 
                              relevant_files: List[Dict[str, str]]) -> str:
    """Enhance ticket description with codebase insights"""
    
    enhanced_parts = [description]
    
    if suggestions:
        enhanced_parts.append("\n## Implementation Guidance")
        for suggestion in suggestions[:3]:  # Top 3 suggestions
            enhanced_parts.append(f"- {suggestion['description']}")
    
    if relevant_files:
        enhanced_parts.append("\n## Reference Files")
        enhanced_parts.append("Consider these existing implementations:")
        for file_info in relevant_files[:5]:  # Top 5 files
            functions = ', '.join(file_info['functions'][:3])
            enhanced_parts.append(f"- `{file_info['path']}` - {functions if functions else 'N/A'}")
    
    return '\n'.join(enhanced_parts)


def _estimate_ticket_complexity(relevant_files: List[Dict[str, str]], 
                               suggestions: List[Dict[str, str]]) -> str:
    """Estimate ticket complexity based on codebase analysis"""
    
    if not relevant_files:
        return 'medium'  # Default when no context available
    
    # Count high-complexity indicators
    complexity_indicators = 0
    
    # Check if many files are involved
    if len(relevant_files) > 5:
        complexity_indicators += 1
    
    # Check for complex suggestions
    complex_keywords = ['integration', 'architecture', 'database', 'migration', 'refactor']
    for suggestion in suggestions:
        if any(keyword in suggestion['description'].lower() for keyword in complex_keywords):
            complexity_indicators += 1
    
    # Check file types - some are inherently more complex
    complex_file_patterns = ['models.py', 'settings.py', 'migrations/', 'api/', 'serializers.py']
    for file_info in relevant_files:
        if any(pattern in file_info['path'] for pattern in complex_file_patterns):
            complexity_indicators += 1
    
    # Determine complexity
    if complexity_indicators >= 3:
        return 'complex'
    elif complexity_indicators >= 1:
        return 'medium'
    else:
        return 'simple'


# Integration with existing AI tools

def get_enhanced_context_prompt(project_id: str, 
                              user_message: str, 
                              user: Optional[User] = None) -> str:
    """
    Get enhanced context prompt for AI responses that includes codebase context
    
    This function can be called from chat consumers to provide better context
    """
    try:
        context_result = get_codebase_context_for_feature(project_id, user_message, user)
        
        if context_result.get('error'):
            return f"Limited codebase context available: {context_result['context']}"
        
        prompt_parts = [
            "## Codebase Context",
            "The following context from the existing codebase is relevant to your request:",
            "",
            context_result['context'],
            "",
        ]
        
        if context_result['suggestions']:
            prompt_parts.extend([
                "## Implementation Suggestions",
                "",
            ])
            for suggestion in context_result['suggestions']:
                prompt_parts.append(f"- **{suggestion['title']}**: {suggestion['description']}")
            prompt_parts.append("")
        
        if context_result['relevant_files']:
            prompt_parts.extend([
                "## Relevant Files to Consider",
                "",
            ])
            for file_info in context_result['relevant_files'][:5]:
                prompt_parts.append(f"- `{file_info['path']}` ({file_info['language']})")
            prompt_parts.append("")
        
        prompt_parts.extend([
            "Please use this codebase context to provide more accurate and contextually appropriate responses.",
            "Reference existing patterns, suggest modifications to relevant files, and ensure consistency with the current architecture.",
            ""
        ])
        
        return '\n'.join(prompt_parts)
        
    except Exception as e:
        logger.error(f"Error generating enhanced context prompt: {e}")
        return f"Error analyzing codebase context: {str(e)}"