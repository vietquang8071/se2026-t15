import assert from "node:assert/strict";
import test from "node:test";
import { validateAuthForm } from "./auth-validation.ts";

const validValues = {
  name: "Minh Anh",
  email: "minh@example.com",
  password: "securepass",
  confirmPassword: "securepass",
};

test("sign-up accepts a complete matching form", () => {
  assert.deepEqual(validateAuthForm("sign-up", validValues), {});
});

test("sign-up reports required, malformed, short, and mismatched values", () => {
  const errors = validateAuthForm("sign-up", {
    name: " ",
    email: "invalid-address",
    password: "short",
    confirmPassword: "different",
  });
  assert.deepEqual(Object.keys(errors).sort(), [
    "confirmPassword",
    "email",
    "name",
    "password",
  ]);
});

test("sign-in checks credentials without sign-up-only rules", () => {
  assert.deepEqual(
    validateAuthForm("sign-in", {
      name: "",
      email: "member@example.com",
      password: "x",
      confirmPassword: "",
    }),
    {},
  );
});

test("sign-in requires both email and password", () => {
  const errors = validateAuthForm("sign-in", {
    ...validValues,
    email: " ",
    password: "",
  });
  assert.deepEqual(Object.keys(errors).sort(), ["email", "password"]);
});
