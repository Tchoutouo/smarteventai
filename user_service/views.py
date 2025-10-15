import re

from django.core.mail import send_mail
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from user_service.models import UserProfile
from django.conf import settings
from django.template.loader import render_to_string

import logging

logger = logging.getLogger("django")



# Check strong password
def is_strong_password(password):
    return (
        len(password) >= 8 and
        re.search(r'[a-z]', password) and
        re.search(r'[A-Z]', password) and
        re.search(r'\d', password) and
        re.search(r'[^A-Za-z0-9]', password)
    )

# Register view
def register_view(request):
    if request.user.is_authenticated:
        return redirect('/profile/')

    if request.method == "POST":
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        confirm_password = request.POST.get('confirm_password', '')
        role = request.POST.get('role', '')
        context = {
            'first_name': first_name,
            'last_name': last_name,
            'email': email,
            'role': role,
        }

        if not all([first_name, last_name, email, password, confirm_password, role]):
            messages.error(request, "All fields are required.")
            return render(request, 'register.html', context)

        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            messages.error(request, "Invalid email format.")
            return render(request, 'register.html', context)

        if User.objects.filter(username=email).exists():
            messages.error(request, "Email is already registered.")
            return render(request, 'register.html', context)

        if password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return render(request, 'register.html', context)

        if not is_strong_password(password):
            messages.error(request, "Password must have uppercase, lowercase, number, and symbol.")
            return render(request, 'register.html', context)

        if role not in ['attendee', 'organizer', "ambassador"]:
            messages.error(request, "Invalid role selected.")
            return render(request, 'register.html', context)

        user = User.objects.create_user(username=email, email=email, password=password)
        user.first_name = first_name
        user.last_name = last_name
        user.save()
        UserProfile.objects.create(user=user, role=role)

        print('Account created successfully!')
        logger.info(f"User model {user.id} saved")

        # Send verification mail. Handle any exception that could occur.
        try:
            """Send verification mail"""
            from_email = settings.DEFAULT_FROM_EMAIL
            mail_subject = "Account Registration Confirmation"
            to_email = user.email

            server_ip = settings.IP_ADDRESS
            port = "8000"
            login_url = f"http://{server_ip}:{port}/login/"

            msge = render_to_string(
                "email/acc_active_email.txt",
                {
                    "username": user.email,
                    "login_url": login_url,
                },
            )

            msge_html = render_to_string(
                "email/acc_active_email.html",
                {
                    "username": user.username,
                    "login_url": login_url,
                },
            )
            send_mail(
                mail_subject,
                msge,
                from_email,
                [to_email, ],
                fail_silently=False,
                html_message=msge_html,
            )
            logger.info(f"Send verification email for {user.email}")
            logger.info(f"Send New User {user.email} notification to Project...")

            messages.success(request, 'Your account has been  registered successfully!')

        except Exception as e:
            print(e)
            msg = "Error sending the verification message"
            messages.error(request, msg)
            logger.error(f"Error sending the verification message: {e}")

        return render(request, 'register_success.html', {
            'first_name': first_name,
            'last_name': last_name,
        })

    return render(request, 'register.html')

# Login view
def login_view(request):
    if request.user.is_authenticated:
        return redirect('/profile/')
    if request.method == "POST":
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        remember_me = request.POST.get('remember_me')
        user = authenticate(request, username=email, password=password)

        if user:
            login(request, user)
            if not remember_me:
                request.session.set_expiry(0)
            else:
                request.session.set_expiry(3600)

            try:
                profile = user.userprofile
            except UserProfile.DoesNotExist:
                messages.error(request, "User profile not found.")
                return redirect('login')

            if profile.role == "attendee":
                return redirect('my_tickets_attendee', secure_token=profile.secure_token)
            elif profile.role == "organizer":
                return redirect('organizer-dashboard', secure_token=profile.secure_token)
            elif profile.role == "ambassador":
                return redirect('ambassador-dashboard', secure_token=profile.secure_token)
            elif user.is_superuser:
                return redirect('supervisor-panel')
            else:
                messages.warning(request, "Unknown role.")
                return redirect('login')
        else:
            messages.error(request, "Incorrect data, try again.")
            return redirect('login')

    return render(request, 'login.html')

# Logout view
def logout_view(request):
    logout(request)
    return render(request, 'logout.html')

# Profile view
@login_required
def profile_view(request):
    profile = get_object_or_404(UserProfile, user=request.user)
    return render(request, 'profile.html', {
        'user': request.user,
        'role': profile.role
    })

# Edit profile view
@login_required
def edit_profile_view(request):
    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        password = request.POST.get('password', '')
        confirm_password = request.POST.get('confirm_password', '')
        current_password = request.POST.get('current_password', '')

        user = request.user

        if not user.check_password(current_password):
            messages.error(request, "Current password is incorrect.")
            return render(request, 'edit_profile.html', {'user': user})

        if password:
            if password != confirm_password:
                messages.error(request, "Passwords do not match.")
                return render(request, 'edit_profile.html', {'user': user})

        # Update full name
        if full_name:
            parts = full_name.split()
            if len(parts) >= 2:
                user.first_name = parts[0]
                user.last_name = ' '.join(parts[1:])
            else:
                user.first_name = full_name
                user.last_name = ''

        # Update password
        if password:
            user.set_password(password)
            update_session_auth_hash(request, user)

        user.save()
        messages.success(request, "Profile updated successfully.")
        return redirect('profile')

    return render(request, 'edit_profile.html', {'user': request.user})
