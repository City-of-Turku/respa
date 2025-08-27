Push-Location -Path *path-to-project*
./AzureUtil.ps1 deploy
./AzureUtil.ps1 dbimport *path-to-project*/103respa-test.sql
./AzureUtil.ps1 copyfiles apifiles *path-to-project*/media
./AzureUtil.ps1 copyfiles apifiles *path-to-project*/static
./AzureUtil.ps1 copyfiles apifiles *path-to-project*/static_src
./AzureUtil.ps1 build api *path-to-project*
./AzureUtil.ps1 build ui *path-to-varaamo-project*
Pop-Location
