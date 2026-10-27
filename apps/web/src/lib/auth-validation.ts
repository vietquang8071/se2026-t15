export type AuthMode = "sign-in" | "sign-up";

export type AuthValues = {
  name: string;
  email: string;
  password: string;
  confirmPassword: string;
};

export type AuthErrors = Partial<Record<keyof AuthValues, string>>;

export function validateAuthForm(
  mode: AuthMode,
  values: AuthValues,
): AuthErrors {
  const errors: AuthErrors = {};

  if (mode === "sign-up" && !values.name.trim()) {
    errors.name = "Nhập tên của bạn để tiếp tục.";
  }
  if (!values.email.trim()) {
    errors.email = "Nhập địa chỉ email để tiếp tục.";
  } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(values.email.trim())) {
    errors.email = "Nhập địa chỉ email hợp lệ.";
  }
  if (!values.password) {
    errors.password = "Nhập mật khẩu để tiếp tục.";
  } else if (mode === "sign-up" && values.password.length < 8) {
    errors.password = "Mật khẩu cần ít nhất 8 ký tự.";
  }
  if (mode === "sign-up" && values.confirmPassword !== values.password) {
    errors.confirmPassword = "Mật khẩu xác nhận chưa khớp.";
  }

  return errors;
}
