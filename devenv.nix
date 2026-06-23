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
  ];
in
{
  packages = tools;

  languages.nix.enable = true;
  languages.python.enable = true;
}
