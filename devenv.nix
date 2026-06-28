{ pkgs, lib, ... }:

let
  python = pkgs.python313;
  flux-local = python.pkgs.callPackage ./flux-local.nix {
    inherit (pkgs)
      kustomize
      kubernetes-helm
      fluxcd
      git
      ;
    inherit (python.pkgs) pytestCheckHook syrupy anyio;
  };

  flate = pkgs.callPackage ./flate.nix {
    inherit (pkgs) fetchurl stdenvNoCC installShellFiles;
  };

  tools = with pkgs; [
    kubectl
    fluxcd
    kustomize
    kubernetes-helm
    sops
    age
    k9s
    talosctl
    talhelper
    yq-go
    restic
    flux-local
    flate
  ];
in
{
  packages = tools;

  languages.nix.enable = true;
  languages.python.enable = true;

  env.SOPS_AGE_KEY_FILE = "${builtins.getEnv "HOME"}/.config/sops/age/keys.txt";
}
