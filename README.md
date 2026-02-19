## How to use this template

The repository has been tagged as a template repository. This means you can create a new repository based on this code using the [GitHub instructions](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-repository-from-a-template)


### Alternative method: checkout the repository and remove git bindings
Replace `<new-folder-name>` with your desired folder name:
```sh
git clone https://github.com/odense-rpa/process-template.git <new-folder-name>

cd <new-folder-name>

rm -rf .git
git init
git add .
git commit -m "Initial commit from process-template"

git remote add origin <new-repo-url>
git push -u origin main
```

