module.exports = {
  root: true,
  extends: ["universe/native", "universe/shared/typescript-analysis"],
  env: {
    node: true,
  },
  parserOptions: {
    project: "./tsconfig.json",
    tsconfigRootDir: __dirname,
  },
};
