# frontend/Dockerfile
FROM node:18

# Set the working directory
WORKDIR /

# Copy package.json and install dependencies
COPY package.json .
RUN npm install

# Copy the rest of the application code
COPY . .

# Expose the port the app runs on
EXPOSE 50003

# Command to run the frontend server
CMD ["npm", "start"]
