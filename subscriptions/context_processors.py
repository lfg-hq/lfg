from .utils import get_user_credits

def user_credits(request):
    """
    Context processor to add user credits to template context
    """
    if request.user.is_authenticated:
        credits = get_user_credits(request.user)
    else:
        credits = 0
        
    return {
        'user_credits': credits
    } 