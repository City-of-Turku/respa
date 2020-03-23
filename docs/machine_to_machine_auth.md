# Machine to machine authentication
In short “machine to machine” or M2M authentication allows users to log into Respa without going through services like Tunnistamo which require human interacting.

To use M2M authentication:
1. Respa admin creates a new account for the new user.
2. The new user retrieves an authorization token from Respa by creating a POST request:
   * target endpoint <Respa URL>/api-token-auth/
   * header Content-Type application/x-www-form-urlencoded
   * form data:
     * username=*myusername*
     * passoword=*mypassword*
3. Use Respa API with header “Authorization: JWT *mytoken*”.
   * To test M2M authentication works: GET <Respa URL>/v1/user/, should return current user’s info.
   * Authorization tokens expire after a certain amount of time. New token needs to be retrieved at that point.
