import {
  CognitoUserPool,
  CognitoUser,
  AuthenticationDetails,
  CognitoUserSession,
} from "amazon-cognito-identity-js";
import { getRuntimeConfig, setAuthToken } from "./api";

let userPoolInstance: CognitoUserPool | null = null;

export async function getUserPool(): Promise<CognitoUserPool> {
  if (userPoolInstance) return userPoolInstance;
  const config = await getRuntimeConfig();
  userPoolInstance = new CognitoUserPool({
    UserPoolId: config.user_pool_id,
    ClientId: config.user_pool_client_id,
  });
  return userPoolInstance;
}

export async function cognitoSignIn(email: string, password: string): Promise<string> {
  const pool = await getUserPool();
  const cognitoUser = new CognitoUser({
    Username: email,
    Pool: pool,
  });

  const authDetails = new AuthenticationDetails({
    Username: email,
    Password: password,
  });

  return new Promise((resolve, reject) => {
    cognitoUser.authenticateUser(authDetails, {
      onSuccess: (session: CognitoUserSession) => {
        const idToken = session.getIdToken().getJwtToken();
        const sub = session.getIdToken().payload.sub;
        setAuthToken(idToken, email, sub);
        resolve(idToken);
      },
      onFailure: (err) => {
        reject(err);
      },
      newPasswordRequired: () => {
        reject(new Error("Password change required by administrator"));
      },
    });
  });
}

export async function cognitoSignUp(email: string, password: string): Promise<string> {
  const pool = await getUserPool();
  return new Promise((resolve, reject) => {
    pool.signUp(email, password, [], [], (err, result) => {
      if (err) {
        let msg = err.message || "Failed to sign up";
        if (msg.includes("PreSignUp") || msg.includes("not allowed")) {
          msg = "Your email domain or address is not on the CloudTrain allow-list.";
        }
        reject(new Error(msg));
        return;
      }
      resolve(result?.userSub || email);
    });
  });
}

export async function cognitoConfirmSignUp(email: string, code: string): Promise<void> {
  const pool = await getUserPool();
  const cognitoUser = new CognitoUser({
    Username: email,
    Pool: pool,
  });

  return new Promise((resolve, reject) => {
    cognitoUser.confirmRegistration(code, true, (err) => {
      if (err) reject(err);
      else resolve();
    });
  });
}

export async function cognitoForgotPassword(email: string): Promise<void> {
  const pool = await getUserPool();
  const cognitoUser = new CognitoUser({
    Username: email,
    Pool: pool,
  });

  return new Promise((resolve, reject) => {
    cognitoUser.forgotPassword({
      onSuccess: () => resolve(),
      onFailure: (err) => reject(err),
    });
  });
}

export async function cognitoConfirmPassword(
  email: string,
  code: string,
  newPass: string
): Promise<void> {
  const pool = await getUserPool();
  const cognitoUser = new CognitoUser({
    Username: email,
    Pool: pool,
  });

  return new Promise((resolve, reject) => {
    cognitoUser.confirmPassword(code, newPass, {
      onSuccess: () => resolve(),
      onFailure: (err) => reject(err),
    });
  });
}

export function signOut(): void {
  setAuthToken(null);
}

export function localBypassSignIn(email = "engineer@cloudtrain.local", sub = "local-user"): void {
  setAuthToken("local-bypass-jwt", email, sub);
}
