"use client";

import Link from "next/link";
import { useState } from "react";
import type { FormEvent } from "react";
import Icon from "./icon";
import { Brand, Button, TextField, ThemeToggle } from "./ui";
import { validateAuthForm } from "@/lib/auth-validation";
import type { AuthMode, AuthErrors } from "@/lib/auth-validation";

export default function AuthForm({ mode }: { mode: AuthMode }) {
  const isSignUp = mode === "sign-up";
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [errors, setErrors] = useState<AuthErrors>({});
  const [submitted, setSubmitted] = useState(false);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextErrors = validateAuthForm(mode, {
      name,
      email,
      password,
      confirmPassword,
    });
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length === 0) {
      setPassword("");
      setConfirmPassword("");
      setSubmitted(true);
    }
  }

  return (
    <div className="auth-layout">
      <aside className="auth-story">
        <Brand />
        <div className="auth-story-content">
          <span className="auth-story-kicker">Từ cuộc họp đến hành động</span>
          <p className="auth-story-headline">Giữ mọi quyết định ở đúng chỗ.</p>
          <p>
            Một không gian gọn gàng để xem transcript, việc cần làm, quyết định
            và các mốc tiếp theo.
          </p>
          <div className="auth-preview" aria-label="Các phần của biên bản mẫu">
            <div className="auth-preview-heading">
              <Icon name="document" size={17} /> Biên bản cuộc họp{" "}
              <span>06 phần</span>
            </div>
            <div className="auth-preview-row">
              <span>01</span> Tóm tắt cuộc họp <Icon name="check" size={16} />
            </div>
            <div className="auth-preview-row">
              <span>02</span> Công việc cần làm <Icon name="check" size={16} />
            </div>
            <div className="auth-preview-row">
              <span>03</span> Quyết định <Icon name="check" size={16} />
            </div>
          </div>
        </div>
        <p className="auth-story-footer">
          Bản xem trước giao diện · Dữ liệu minh họa
        </p>
      </aside>

      <main className="auth-main">
        <div className="auth-topbar">
          <Brand />
          <span>Bản demo frontend</span>
          <ThemeToggle />
        </div>
        <div className="auth-panel">
          {submitted ? (
            <div className="auth-success" role="status">
              <span className="auth-success-icon">
                <Icon name="check" size={25} />
              </span>
              <p className="eyebrow">Hoàn tất biểu mẫu</p>
              <h1>{isSignUp ? "Sẵn sàng khám phá" : "Chào mừng trở lại"}</h1>
              <p>
                Thông tin đã được kiểm tra trong bản demo. Chưa có tài khoản
                hoặc phiên đăng nhập nào được tạo.
              </p>
              <Link className="primary-button" href="/">
                Mở workspace <Icon name="chevron-right" size={16} />
              </Link>
              <button
                type="button"
                className="auth-reset"
                onClick={() => setSubmitted(false)}
              >
                Quay lại biểu mẫu
              </button>
            </div>
          ) : (
            <>
              <span className="auth-kicker">
                {isSignUp ? "BẮT ĐẦU" : "RẤT VUI KHI BẠN QUAY LẠI"}
              </span>
              <h1>{isSignUp ? "Tạo tài khoản" : "Đăng nhập"}</h1>
              <p className="auth-intro">
                {isSignUp
                  ? "Thử giao diện tạo tài khoản và khám phá workspace mẫu."
                  : "Thử giao diện đăng nhập để tiếp tục tới workspace mẫu."}
              </p>
              <div className="auth-demo-note">
                <Icon name="info" size={17} />
                <span>
                  Đây là bản demo giao diện. Biểu mẫu không gửi hoặc lưu thông
                  tin của bạn.
                </span>
              </div>
              <form className="auth-form" onSubmit={submit} noValidate>
                {isSignUp && (
                  <TextField
                    id="auth-name"
                    label="Họ và tên"
                    type="text"
                    autoComplete="name"
                    placeholder="Nguyễn Minh Anh"
                    value={name}
                    required
                    error={errors.name}
                    onChange={(event) => {
                      setName(event.target.value);
                      setErrors((current) => ({ ...current, name: undefined }));
                    }}
                  />
                )}
                <TextField
                  id="auth-email"
                  label="Email"
                  type="email"
                  inputMode="email"
                  autoComplete="email"
                  placeholder="ban@congty.com"
                  value={email}
                  required
                  error={errors.email}
                  onChange={(event) => {
                    setEmail(event.target.value);
                    setErrors((current) => ({ ...current, email: undefined }));
                  }}
                />
                <TextField
                  id="auth-password"
                  label="Mật khẩu"
                  type="password"
                  autoComplete={isSignUp ? "new-password" : "current-password"}
                  placeholder={isSignUp ? "Ít nhất 8 ký tự" : "Nhập mật khẩu"}
                  value={password}
                  required
                  error={errors.password}
                  hint={
                    isSignUp ? "Dùng ít nhất 8 ký tự cho bản demo." : undefined
                  }
                  onChange={(event) => {
                    setPassword(event.target.value);
                    setErrors((current) => ({
                      ...current,
                      password: undefined,
                    }));
                  }}
                />
                {isSignUp && (
                  <TextField
                    id="auth-confirm-password"
                    label="Xác nhận mật khẩu"
                    type="password"
                    autoComplete="new-password"
                    placeholder="Nhập lại mật khẩu"
                    value={confirmPassword}
                    required
                    error={errors.confirmPassword}
                    onChange={(event) => {
                      setConfirmPassword(event.target.value);
                      setErrors((current) => ({
                        ...current,
                        confirmPassword: undefined,
                      }));
                    }}
                  />
                )}
                <Button className="auth-submit" type="submit">
                  {isSignUp ? "Tạo tài khoản demo" : "Đăng nhập demo"}
                  <Icon name="chevron-right" size={16} />
                </Button>
              </form>
              <p className="auth-switch">
                {isSignUp ? "Đã có tài khoản?" : "Chưa có tài khoản?"}{" "}
                <Link href={isSignUp ? "/sign-in" : "/sign-up"}>
                  {isSignUp ? "Đăng nhập" : "Tạo tài khoản"}
                </Link>
              </p>
              <Link href="/" className="auth-home-link">
                <Icon name="arrow-left" size={15} /> Vào workspace mẫu
              </Link>
            </>
          )}
        </div>
        <p className="auth-footnote">
          Meeting Minutes Assistant · Frontend demo
        </p>
      </main>
    </div>
  );
}
