from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.core.mail import send_mail
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from .models import Profile

class EmailAuthenticationForm(AuthenticationForm):
    """
    Custom authentication form that uses email for login
    """
    username = forms.EmailField(
        label=_("Email"),
        widget=forms.EmailInput(attrs={"autocomplete": "email", "class": "form-input", "placeholder": "Enter your email"}),
    )
    
    error_messages = {
        "invalid_login": _(
            "Please enter a correct email and password. Note that both fields may be case-sensitive."
        ),
        "inactive": _("This account is inactive."),
    }

class UserRegisterForm(UserCreationForm):
    email = forms.EmailField()
    
    class Meta:
        model = User
        fields = ['email', 'password1', 'password2']
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data['email']  # Set username to email
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
            # Send welcome email using Django's console backend for development
            try:
                send_mail(
                    subject='Welcome to LFG',
                    message=f'Hi there,\n\nThank you for joining LFG! Your account has been created successfully.\n\nRegards,\nThe LFG Team',
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=True,  # Don't raise exceptions for email errors
                )
            except Exception as e:
                # Log the error but don't prevent account creation
                print(f"Error sending welcome email: {e}")
        return user

class UserUpdateForm(forms.ModelForm):
    email = forms.EmailField()
    
    class Meta:
        model = User
        fields = ['email']
        
    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data['email']  # Update username when email changes
        if commit:
            user.save()
        return user

class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['bio', 'avatar'] 