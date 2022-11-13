ATM have to comment out BGP (i think???)
helm template cilium cilium/cilium -f cni/values.yaml -n kube-system > cni/install.yaml


 1. apply-config to first node
 2. bootstrap
 3. comment out bgp and generate cni config `helm template cilium cilium/cilium -f cni/values.yaml -n kube-system > cni/install.yaml`
 4. apply cni yaml
 5. apply-config for other nodes
 6. uncomment bgp and genreate cni config
 7. apply sops secret
 8. bootsrap flux
    
	requires a github PAT with read/write for administration and content on the homelab repo



talosctl --talosconfig ./talosconfig bootstrap




thoughts:
 - start w/ standard networking, then apply cilium after bootstrap (maybe w/ flux???)
   - actually starting with cilium would be ncie but idk how
