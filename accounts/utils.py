from django.db.models import Sum, Count
from django.utils import timezone
from datetime import timedelta
from accounts.models import TokenUsage


def get_token_usage_stats(user=None, project=None, conversation=None, days=30):
    """
    Get token usage statistics for a user, project, or conversation
    
    Args:
        user: User object (optional)
        project: Project object (optional)
        conversation: Conversation object (optional)
        days: Number of days to look back (default: 30)
    
    Returns:
        Dictionary with usage statistics
    """
    # Build the base query
    query = TokenUsage.objects.all()
    
    # Apply filters
    if user:
        query = query.filter(user=user)
    if project:
        query = query.filter(project=project)
    if conversation:
        query = query.filter(conversation=conversation)
    
    # Filter by date range
    start_date = timezone.now() - timedelta(days=days)
    query = query.filter(timestamp__gte=start_date)
    
    # Get aggregate statistics
    stats = query.aggregate(
        total_input_tokens=Sum('input_tokens'),
        total_output_tokens=Sum('output_tokens'),
        total_tokens=Sum('total_tokens'),
        total_cost=Sum('cost'),
        request_count=Count('id')
    )
    
    # Get per-provider statistics
    provider_stats = query.values('provider').annotate(
        input_tokens=Sum('input_tokens'),
        output_tokens=Sum('output_tokens'),
        total_tokens=Sum('total_tokens'),
        cost=Sum('cost'),
        requests=Count('id')
    )
    
    # Get per-model statistics
    model_stats = query.values('provider', 'model').annotate(
        input_tokens=Sum('input_tokens'),
        output_tokens=Sum('output_tokens'),
        total_tokens=Sum('total_tokens'),
        cost=Sum('cost'),
        requests=Count('id')
    )
    
    return {
        'summary': stats,
        'by_provider': list(provider_stats),
        'by_model': list(model_stats),
        'date_range': {
            'start': start_date,
            'end': timezone.now(),
            'days': days
        }
    }


def get_daily_token_usage(user=None, project=None, days=7):
    """
    Get daily token usage for charts
    
    Args:
        user: User object (optional)
        project: Project object (optional)
        days: Number of days to look back (default: 7)
    
    Returns:
        List of daily usage data
    """
    query = TokenUsage.objects.all()
    
    if user:
        query = query.filter(user=user)
    if project:
        query = query.filter(project=project)
    
    start_date = timezone.now() - timedelta(days=days)
    query = query.filter(timestamp__gte=start_date)
    
    # Group by date
    daily_usage = query.extra(
        select={'date': 'DATE(timestamp)'}
    ).values('date').annotate(
        tokens=Sum('total_tokens'),
        cost=Sum('cost'),
        requests=Count('id')
    ).order_by('date')
    
    return list(daily_usage)