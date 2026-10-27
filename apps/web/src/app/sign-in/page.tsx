import type { Metadata } from "next";
import AuthForm from "../_components/auth-form";

export const metadata: Metadata = {
  title: "Đăng nhập | Meeting Minutes Assistant",
};

export default function SignInPage() {
  return <AuthForm mode="sign-in" />;
}
