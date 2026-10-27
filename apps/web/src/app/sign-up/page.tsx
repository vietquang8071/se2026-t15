import type { Metadata } from "next";
import AuthForm from "../_components/auth-form";

export const metadata: Metadata = {
  title: "Tạo tài khoản | Meeting Minutes Assistant",
};

export default function SignUpPage() {
  return <AuthForm mode="sign-up" />;
}
