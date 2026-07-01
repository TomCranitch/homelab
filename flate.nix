{
  lib,
  stdenvNoCC,
  fetchurl,
  installShellFiles,
}:

let
  version = "0.4.9";

  goarch = {
    x86_64 = "amd64";
    aarch64 = "arm64";
  }.${stdenvNoCC.hostPlatform.parsed.cpu.name} or stdenvNoCC.hostPlatform.parsed.cpu.name;

  goos = stdenvNoCC.hostPlatform.parsed.kernel.name;
in
stdenvNoCC.mkDerivation {
  pname = "flate";
  inherit version;

  src = fetchurl {
    url = "https://github.com/home-operations/flate/releases/download/v${version}/flate_${version}_${goos}_${goarch}.tar.gz";
    hash = "sha256-QbjdzihxOfj31cSerWXj2Q7lgArfDi4Q5BCT8cwBjso=";
  };

  dontConfigure = true;
  dontBuild = true;
  dontFixup = true;
  dontUnpack = true;

  nativeBuildInputs = [ installShellFiles ];

  installPhase = ''
    mkdir -p $out/bin
    tar xzf $src -C $out/bin flate
    chmod +x $out/bin/flate

    installShellCompletion --cmd flate \
      --bash <($out/bin/flate completion bash) \
      --fish <($out/bin/flate completion fish) \
      --zsh <($out/bin/flate completion zsh)
  '';

  meta = with lib; {
    description = "Render and diff Flux GitOps repositories fully offline — one static binary";
    homepage = "https://github.com/home-operations/flate";
    license = licenses.agpl3Only;
    mainProgram = "flate";
    platforms = platforms.linux ++ platforms.darwin;
  };
}
