# -*- mode: ruby -*-
# vi: set ft=ruby :

VAGRANTFILE_API_VERSION = "2"

Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|
  config.vm.box = "chef/centos-7.0"
  config.vm.network "private_network", ip: "192.168.50.17"
  ## config.vm.synced_folder "..", "/vagrant/odl-ci"

  config.vm.provider "virtualbox" do |vb|
      vb.cpus = 4
      vb.memory = 6144
  end

  config.vm.provision "shell", path: "./bootstrap.sh"

end
