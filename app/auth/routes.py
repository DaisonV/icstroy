from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user
from sqlalchemy import select

from . import bp
from ..extensions import db
from ..models import User


def is_safe_url(target):
    if not target:
        return False
    host_url = urlparse(request.host_url)
    redirect_url = urlparse(urljoin(request.host_url, target or ""))
    return redirect_url.scheme in ("http", "https") and host_url.netloc == redirect_url.netloc


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("crm.dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = db.session.scalar(select(User).where(User.email == email))
        if user and user.is_active and user.check_password(password):
            user.last_login_at = datetime.now(timezone.utc)
            db.session.commit()
            login_user(user, remember=bool(request.form.get("remember")))
            next_url = request.args.get("next")
            return redirect(next_url if is_safe_url(next_url) else url_for("crm.dashboard"))
        flash("Неверный email или пароль.", "error")

    return render_template("auth/login.html")


@bp.post("/logout")
def logout():
    logout_user()
    flash("Вы вышли из CRM.", "success")
    return redirect(url_for("auth.login"))
