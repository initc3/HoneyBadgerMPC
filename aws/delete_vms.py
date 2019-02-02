import os
from aws.ec2Manager import EC2Manager


if __name__ == "__main__":
    ec2manager = EC2Manager()
    if os.path.isfile(EC2Manager.current_vms_file_name):
        print("Do you want to terminate all VMs with the ids:",
              ec2manager.get_current_vm_instance_ids(), "(y/n)?")

        while True:
            choice = input()
            if choice.lower() == "y":
                ec2manager.terminate_instances_by_id()
                print("Termination triggered successfully!")
                break
            elif choice.lower() == "n":
                print("Termination not triggered.")
                break
            else:
                print("Invalid option, reenter.")
    else:
        print("No VMs to delete.")
