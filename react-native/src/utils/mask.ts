export const maskToken = (token: string) => {
  if (!token) return "";
  if (token.length <= 8) return token;
  return `${token.slice(0, 4)}...${token.slice(-4)}`;
};
