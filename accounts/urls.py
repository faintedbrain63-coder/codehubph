from django.urls import path

from accounts import views

app_name = "accounts"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("purchases/", views.dashboard, {"customer_view": True}, name="purchases"),
    path("register/", views.register, name="register"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("profile/", views.profile, name="profile"),
    path("settings/", views.settings, name="settings"),
    path("review/", views.testimonial, name="testimonial"),
    path("project-reviews/", views.project_reviews, name="project_reviews"),
    path("project-reviews/<int:pk>/", views.project_testimonial, name="project_testimonial"),
    path("onboarding/done/", views.onboarding_done, name="onboarding_done"),
    path("password/", views.PasswordChangeView.as_view(), name="password_change"),
    path("password-reset/", views.PasswordResetView.as_view(), name="password_reset"),
    path("password-reset/sent/", views.PasswordResetDoneView.as_view(), name="password_reset_done"),
    path(
        "password-reset/<uidb64>/<token>/",
        views.PasswordResetConfirmView.as_view(),
        name="password_reset_confirm",
    ),
    path(
        "password-reset/complete/",
        views.PasswordResetCompleteView.as_view(),
        name="password_reset_complete",
    ),
]
