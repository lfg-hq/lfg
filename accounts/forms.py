from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm, PasswordResetForm as BasePasswordResetForm
from django.core.mail import send_mail
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from .models import Profile, Organization, OrganizationMembership, OrganizationInvitation
from django.core.exceptions import ValidationError

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
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        # Check both email and username fields since we use email as username
        if User.objects.filter(email=email).exists() or User.objects.filter(username=email).exists():
            raise ValidationError("A user with this email already exists.")
        return email
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data['email']  # Set username to email
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
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


class PasswordResetForm(BasePasswordResetForm):
    """
    Custom password reset form that finds users by email
    (since we use email as username)
    """
    email = forms.EmailField(
        label=_("Email"),
        max_length=254,
        widget=forms.EmailInput(attrs={
            'class': 'form-input',
            'placeholder': 'Enter your email address',
            'autocomplete': 'email'
        })
    )
    
    def get_users(self, email):
        """
        Override to find users by email field regardless of username
        """
        active_users = User.objects.filter(
            email__iexact=email,
            is_active=True
        )
        return (u for u in active_users if u.has_usable_password())


class OrganizationCreationForm(forms.ModelForm):
    """Form for creating a new organization"""
    
    class Meta:
        model = Organization
        fields = ['name', 'description', 'avatar', 'allow_member_invites']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Enter organization name',
                'maxlength': 100
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-input',
                'placeholder': 'Describe your organization (optional)',
                'rows': 3,
                'maxlength': 500
            }),
            'avatar': forms.FileInput(attrs={
                'class': 'form-input',
                'accept': 'image/*'
            }),
            'allow_member_invites': forms.CheckboxInput(attrs={
                'class': 'form-checkbox'
            })
        }
        labels = {
            'allow_member_invites': 'Allow members to invite others',
        }
        help_texts = {
            'allow_member_invites': 'If enabled, regular members can invite new people to the organization.',
        }
    
    def clean_name(self):
        name = self.cleaned_data.get('name')
        if name:
            # Check for existing organization with similar name
            existing = Organization.objects.filter(name__iexact=name)
            if self.instance and self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise ValidationError("An organization with this name already exists.")
        return name


class OrganizationUpdateForm(forms.ModelForm):
    """Form for updating organization details"""
    
    class Meta:
        model = Organization
        fields = ['name', 'description', 'avatar', 'allow_member_invites']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-input',
                'maxlength': 100
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-input',
                'rows': 3,
                'maxlength': 500
            }),
            'avatar': forms.FileInput(attrs={
                'class': 'form-input',
                'accept': 'image/*'
            }),
            'allow_member_invites': forms.CheckboxInput(attrs={
                'class': 'form-checkbox'
            })
        }
        labels = {
            'allow_member_invites': 'Allow members to invite others',
        }
    
    def clean_name(self):
        name = self.cleaned_data.get('name')
        if name:
            existing = Organization.objects.filter(name__iexact=name)
            if self.instance and self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise ValidationError("An organization with this name already exists.")
        return name


class OrganizationInvitationForm(forms.Form):
    """Form for inviting members to an organization"""
    
    email = forms.EmailField(
        label="Email Address",
        widget=forms.EmailInput(attrs={
            'class': 'form-input',
            'placeholder': 'Enter email address',
            'autocomplete': 'email'
        }),
        help_text="Enter the email address of the person you want to invite."
    )
    
    role = forms.ChoiceField(
        choices=OrganizationMembership.ROLE_CHOICES,
        initial='member',
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Select the role for the new member."
    )
    
    message = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-input',
            'rows': 3,
            'placeholder': 'Add a personal message (optional)',
            'maxlength': 500
        }),
        help_text="Optional message to include in the invitation email."
    )
    
    def __init__(self, *args, **kwargs):
        self.organization = kwargs.pop('organization', None)
        self.inviter = kwargs.pop('inviter', None)
        super().__init__(*args, **kwargs)
        
        # Limit role choices based on inviter's permissions
        if self.inviter and self.organization:
            inviter_role = self.organization.get_user_role(self.inviter)
            if inviter_role == 'admin':
                # Admins can't invite owners
                self.fields['role'].choices = [
                    choice for choice in OrganizationMembership.ROLE_CHOICES 
                    if choice[0] != 'owner'
                ]
            elif inviter_role == 'member':
                # Members can only invite other members
                self.fields['role'].choices = [('member', 'Member')]
                self.fields['role'].initial = 'member'
                self.fields['role'].widget = forms.HiddenInput()
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email and self.organization:
            # Check if user is already a member
            if User.objects.filter(
                email__iexact=email,
                organization_memberships__organization=self.organization,
                organization_memberships__status='active'
            ).exists():
                raise ValidationError("This user is already a member of the organization.")
            
            # Check for pending invitation
            if OrganizationInvitation.objects.filter(
                organization=self.organization,
                email__iexact=email,
                status='pending'
            ).exists():
                raise ValidationError("A pending invitation already exists for this email.")
        
        return email


class MembershipUpdateForm(forms.ModelForm):
    """Form for updating member roles"""
    
    class Meta:
        model = OrganizationMembership
        fields = ['role']
        widgets = {
            'role': forms.Select(attrs={'class': 'form-select'})
        }
    
    def __init__(self, *args, **kwargs):
        self.current_user = kwargs.pop('current_user', None)
        super().__init__(*args, **kwargs)
        
        # Prevent users from changing their own role
        if (self.instance and self.current_user and 
            self.instance.user == self.current_user):
            self.fields['role'].widget.attrs['disabled'] = True
        
        # Limit role choices for non-owners
        if (self.current_user and self.instance and 
            self.instance.organization.get_user_role(self.current_user) != 'owner'):
            # Non-owners can't set owner role
            self.fields['role'].choices = [
                choice for choice in OrganizationMembership.ROLE_CHOICES 
                if choice[0] != 'owner'
            ]


class OrganizationSwitchForm(forms.Form):
    """Form for switching organization context"""
    
    organization = forms.ModelChoiceField(
        queryset=Organization.objects.none(),
        empty_label="Personal Space",
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if user:
            # Show organizations where user is an active member
            self.fields['organization'].queryset = Organization.objects.filter(
                memberships__user=user,
                memberships__status='active',
                is_active=True
            ).order_by('name') 