ATM have to comment out BGP (i think???)
helm template cilium cilium/cilium -f cni/values.yaml -n kube-system > cni/install.yaml
kustomize build --enable-helm > install.yaml



 1. apply-config to first node
 2. bootstrap
 3. comment out bgp and generate cni config `helm template cilium cilium/cilium -f cni/values.yaml -n kube-system > cni/install.yaml`
 4. apply cni yaml
 5. apply-config for other nodes
 8. bootsrap flux: flux bootstrap github --owner=TomCranitch  --repository=homelab --branch=main --path=./cluster/flux 
 7. once the flux-system namespace is created: apply sops secret: cat ~/.config/sops/age/keys.txt | kubectl create secret generic sops-age -n flux-system --from-file=age.agekey=/dev/stdin
 6. uncomment bgp and genreate cni config
    
	requires a github PAT with read/write for administration and content on the homelab repo



 6. uncomment bgp and genreate cni config
 	requires pvc


talosctl --talosconfig ./talosconfig bootstrap




thoughts:
 - start w/ standard networking, then apply cilium after bootstrap (maybe w/ flux???)
   - actually starting with cilium would be ncie but idk how
