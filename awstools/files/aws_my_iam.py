#!/usr/bin/env python3

import boto3, json
import pprint

def debug(msg):
    print("[DEBUG] {}".format(msg))


def getProfiles():
    client = boto3.client('iam')
    response = client.list_instance_profiles()
    out = {}
        
    for prof in response["InstanceProfiles"]:
        profname, roles = prof["InstanceProfileName"], [x["RoleName"] for x in prof["Roles"]]
        out[profname] = {}
        for role in roles:
            response = client.list_attached_role_policies(RoleName=role)
            policies = [(pol["PolicyName"], pol["PolicyArn"]) for pol in response["AttachedPolicies"]]
            out[profname][role] = policies

    return out

def listProfiles():
    client = boto3.client('iam')
    for profname, roles in sorted(getProfiles().items()):
        print("{}".format(profname))
        for role, policies in sorted(roles.items()):
            print(" - Role: {}".format(role))
            for pol, arn in sorted(policies):
                print("   - {}    ({})".format(pol, arn))

def getAllPolicies():
    client = boto3.client('iam')
    response = client.list_policies(Scope="All")
    return dict([(x["PolicyName"], x["Arn"]) for x in response["Policies"]])

def listPolicies():
    pols = getAllPolicies()
    print("\n".join(["{}\t({})".format(p,a) for (p,a) in sorted(pols.items(), key=lambda tup: tup[0])]))

def createProfile(name, policies):
    client = boto3.client('iam')

    policyDict = getAllPolicies()
    fail = False

    policies = list(set(policies))
    for pol in policies:
        if pol not in policyDict:
            debug("ERROR: policy {} does not exist".format(pol))
            pprint.pprint(policyDict)
            fail = True

    if fail:
        print("ERROR: some policies do not exist, use the listpolicies subcommand to see them all")
        return

    debug("Creating instance profile {}".format(name))
    response = client.create_instance_profile(InstanceProfileName=name)
    debug("Creating role {}".format(name))
    response = client.create_role(RoleName=name, AssumeRolePolicyDocument=json.dumps({'Statement': [{'Action': 'sts:AssumeRole', 'Effect': 'Allow', 'Principal': {'Service': 'ec2.amazonaws.com'}}], 'Version': '2012-10-17'}))

    for pol in sorted(policies):
        debug("Adding policy {} ({})".format(pol, policyDict[pol]))
        client.attach_role_policy(RoleName=name, PolicyArn=policyDict[pol])

    debug("Adding role {} to instance profile {}".format(name, name))
    client.add_role_to_instance_profile(InstanceProfileName=name, RoleName=name)

def removeProfile(name, removeRoles=True):
    client = boto3.client('iam')
    policyDict = getAllPolicies()
    profiles = getProfiles()

    if name not in profiles:
        debug("Profile {} does not exist".format(name))
        return

    # get list of roles and remove_role_from_instance_profile all of them
    roles = profiles[name]
    for role, policies in roles.items():
        debug("Removing role {} from instance profile {}".format(role, name))
        client.remove_role_from_instance_profile(InstanceProfileName=name, RoleName=role)

        if removeRoles:
            # delete the role
            for pol, arn in policies:
                debug("Detaching policy {} (ARN {}) from role {}".format(pol, arn, role))
                client.detach_role_policy(RoleName=name, PolicyArn=arn)
            client.delete_role(RoleName=role)
            debug("Deleted role {}".format(role))

    client.delete_instance_profile(InstanceProfileName=name)
    debug("Deleted instance profile {}".format(name))

            

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Create or remove IAM profiles on Amazon EC2")
    subparsers = parser.add_subparsers(dest="cmd")

    create = subparsers.add_parser('create')
    create.add_argument('name', type=str, help="Name of the instance profile")
    create.add_argument('profilename', type=str, default="", help="profiles to add", nargs='+')

    remove = subparsers.add_parser('remove')
    remove.add_argument('name', type=str, help="Name of the instance profile")

    listcmd = subparsers.add_parser('list')
    listpoliciescmd = subparsers.add_parser('listpolicies')

    args = parser.parse_args()

    if args.cmd == "create":
        createProfile(args.name, args.profilename)
    elif args.cmd == "remove":
        removeProfile(args.name)
    elif args.cmd == "list":
        listProfiles()
    elif args.cmd == "listpolicies":
        listPolicies()
    else:
        parser.print_help()

