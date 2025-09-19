from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.models import User
from .forms import ClientSignUpForm
from .models import UserProfile


def register(request):
    """Регистрация пользователя"""
    author_signup = request.GET.get('author') == '1'
    if request.method == 'POST':
        author_signup = request.POST.get('author_signup') == '1'
        form = ClientSignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            username = form.cleaned_data.get('username')
            if hasattr(user, 'profile'):
                user.profile.is_contributor = author_signup
                user.profile.save(update_fields=['is_contributor'])
            messages.success(request, f'Аккаунт для {username} был создан!')
            
            # Автоматический вход после регистрации
            user = authenticate(username=form.cleaned_data['username'],
                              password=form.cleaned_data['password1'])
            if user is not None:
                login(request, user)
                return redirect('gallery:home')
    else:
        form = ClientSignUpForm()
    
    return render(request, 'accounts/register.html', {'form': form, 'author_signup': author_signup})


def login_view(request):
    """Вход пользователя"""
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            next_url = request.GET.get('next', 'gallery:home')
            return redirect(next_url)
        else:
            messages.error(request, 'Неверные учетные данные')
    
    return render(request, 'accounts/login.html')


def logout_view(request):
    """Выход пользователя"""
    logout(request)
    messages.success(request, 'Вы успешно вышли из системы')
    return redirect('gallery:home')


@login_required
def profile(request):
    """Профиль пользователя"""
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        # Обновление профиля
        profile.bio = request.POST.get('bio', profile.bio)
        profile.website = request.POST.get('website', profile.website)
        profile.location = request.POST.get('location', profile.location)
        profile.email_notifications = 'email_notifications' in request.POST
        profile.public_profile = 'public_profile' in request.POST
        
        if 'avatar' in request.FILES:
            profile.avatar = request.FILES['avatar']
        
        profile.save()
        messages.success(request, 'Профиль обновлен!')
        return redirect('accounts:profile')
    
    # Обновляем статистику
    profile.update_stats()
    
    return render(request, 'accounts/profile.html', {'profile': profile})


def public_profile(request, username):
    """Публичный профиль пользователя"""
    try:
        user = User.objects.get(username=username)
        profile = user.profile
        
        if not profile.public_profile:
            messages.error(request, 'Профиль пользователя закрыт')
            return redirect('gallery:home')
        
        # Получаем фотографии пользователя
        photos = user.photo_set.filter(is_approved=True)[:12]
        
        context = {
            'profile_user': user,
            'profile': profile,
            'photos': photos,
        }
        
        return render(request, 'accounts/public_profile.html', context)
        
    except User.DoesNotExist:
        messages.error(request, 'Пользователь не найден')
        return redirect('gallery:home')
