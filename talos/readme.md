ATM have to comment out BGP (i think???)
helm template cilium cilium/cilium -f cni/values.yaml -n kube-system > cni/install.yaml


192.168.29.10 - homeprod-cVIP
192.168.29.11 - homeprod-c01
192.168.29.21 - homeprod-w01



talosctl --talosconfig ./talosconfig bootstrap



thoughts:
 - start w/ standard networking, then apply cilium after bootstrap (maybe w/ flux???)
   - actually starting with cilium would be ncie but idk how
