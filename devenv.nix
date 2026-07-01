{ pkgs, lib, ... }:

let
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
    flate
  ];
in
{
  packages = tools;

  languages.nix.enable = true;
  languages.python.enable = true;

  env.SOPS_AGE_KEY_FILE = "${builtins.getEnv "HOME"}/.config/sops/age/keys.txt";
}
