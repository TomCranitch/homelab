{
  buildPythonPackage,
  fetchFromGitHub,
  lib,
  setuptools,
  setuptools-scm,

  # propagatedBuildInputs
  pyyaml,
  gitpython,
  aiofiles,
  mashumaro,
  nest-asyncio,
  oras,
  pytest,
  pytest-asyncio,
  python-slugify,
  pytestCheckHook,

  # checkInputs
  kustomize,
  kubernetes-helm,
  syrupy,
  anyio,
  fluxcd,
  git,
}:
buildPythonPackage rec {
  pname = "flux_local";
  version = "8.1.0";
  pyproject = true;

  src = fetchFromGitHub {
    owner = "allenporter";
    repo = "flux-local";
    rev = version;
    hash = "sha256-kTfGqvva39o5PQInpBiwjr4sNIf0I6YqloqWUXGhOLY=";
  };

  nativeBuildInputs = [
    setuptools
    setuptools-scm
  ];

  propagatedBuildInputs = [
    pyyaml
    gitpython
    aiofiles
    mashumaro
    nest-asyncio
    oras
    pytest
    pytest-asyncio
    python-slugify
  ];

  nativeCheckInputs = [
  ];

  doCheck = false;

  meta = with lib; {
    description = "flux-local is a set of tools and libraries for managing a local flux gitops repository";
    homepage = "https://github.com/allenporter/flux-local";
    license = licenses.asl20;
    mainProgram = "flux-local";
  };
}
